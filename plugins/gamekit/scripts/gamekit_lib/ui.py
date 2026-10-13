"""`gamekit ui`: a local web page for a game's assets, served on this PC only (127.0.0.1).

The page (plugins/gamekit/ui/index.html) asks this server for JSON and the server does the same work
as the CLI commands. Every request reads assets.yaml again, so edits made by hand or by Claude show
up on the next refresh. One action runs at a time (ACTION); reading state never waits for it.

Adding a tab later (for example an AI generator): a section in index.html plus a handler in GET or POST below.
"""
from __future__ import annotations

import base64
import io
import json
import mimetypes
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, quote, unquote, urlparse

from PIL import Image

from . import (art, aseprite, audio, codeart, credits, engines, made, manifest, music, packs, palette, touchup,
               pictures, pipeline, sfxr)

PAGE = Path(__file__).resolve().parent.parent.parent / "ui" / "index.html"
PLUGIN_JSON = Path(__file__).resolve().parent.parent.parent / ".claude-plugin" / "plugin.json"
UPLOADS = Path(tempfile.gettempdir()) / "gamekit-uploads"
DEFAULT_PORT = 7862          # Hearthtone uses 7861
MAX_UPLOAD = 300 * 1024 * 1024
KNOWN_ERRORS = (manifest.ManifestError, palette.PaletteError, art.ArtError, aseprite.AsepriteError,
                packs.PackError, audio.AudioError, music.MusicError, codeart.CodeArtError, pictures.PictureError,
                engines.EngineError, ValueError)
ACTION = threading.Lock()
mimetypes.add_type("audio/ogg", ".ogg")
mimetypes.add_type("audio/wav", ".wav")


class UserError(Exception):
    """A problem to show on the page as it is (bad request, unknown asset...)."""


# --- reading the game ------------------------------------------------------------------------

def version() -> str:
    """gamekit's version, from the plugin manifest ("" if it can't be read)."""
    try:
        return str(json.loads(PLUGIN_JSON.read_text(encoding="utf-8")).get("version", ""))
    except (OSError, ValueError, AttributeError):
        return ""


def file_url(root: Path, path: Path) -> str | None:
    """/file/... link for a file inside the game folder, with its modified time so the browser reloads changes."""
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    version = int(path.stat().st_mtime) if path.exists() else 0
    return "/file/" + quote(rel.as_posix()) + f"?v={version}"


def asset_json(loaded: manifest.Manifest, a: manifest.Asset) -> dict:
    path = loaded.asset_path(a)
    src = loaded.source_path(a)
    exists = path.exists()
    is_image = path.suffix.lower() == ".png"
    preview = f"/preview/{quote(a.id)}?v={int(path.stat().st_mtime)}" if exists and is_image else None
    from_code = bool(is_image and not exists and codeart.has_art(loaded, a))
    if from_code:  # no file yet: the game still draws it from its code, so show that
        preview = f"/preview/{quote(a.id)}?v={int((loaded.root / loaded.code_art).stat().st_mtime)}"
    lic = a.license
    try:
        lic = manifest.effective_license(loaded, a) if a.license else {}
    except Exception:  # a broken pack.yaml shows up in validate's problems instead
        pass
    return {
        "id": a.id, "kind": a.kind, "source": a.source, "status": a.status, "file": a.file,
        "size": a.size, "frames": a.frames if isinstance(a.frames, dict) else {}, "notes": a.notes,
        "replaces": a.replaces, "loop": loaded.loops(a), "exists": exists,
        "url": file_url(loaded.root, path) if exists and not is_image else None,
        "preview": preview, "from_code": from_code,
        "src": src.relative_to(loaded.root).as_posix() if src is not None else None,
        "src_exists": bool(src and src.exists()),
        "license": lic,
        "targets": pictures.frame_targets(loaded, a) if is_image else [],
        "poses": {t: pictures.pose(loaded, a, t) for t in pictures.frame_targets(loaded, a)}
                 if is_image and loaded.frame_paths(a) else {},
        "animations": _animations(loaded, a) if is_image else {},
    }


def _animations(loaded: manifest.Manifest, a: manifest.Asset) -> dict[str, list[str]]:
    """Animation name -> its frame files' names, in order (frame_files sprites only)."""
    out: dict[str, list[str]] = {}
    for anim, _, path in loaded.frame_paths(a):
        out.setdefault(anim, []).append(path.stem)
    return out


def state(loaded: manifest.Manifest) -> dict:
    counts = {s: 0 for s in manifest.STATUSES}
    for a in loaded.assets:
        if a.status in counts:
            counts[a.status] += 1
    return {
        "game": loaded.game or loaded.root.name,
        "version": version(),
        "root": str(loaded.root.resolve()),
        "manifest": loaded.path.name,
        "frame_files": loaded.frame_files,
        "counts": counts,
        "kinds": list(manifest.KINDS),
        "sources": manifest.SOURCES,
        "statuses": manifest.STATUSES,
        "presets": sfxr.PRESETS,
        "tweaks": sfxr.TWEAKS,
        "sfx_peak_db": loaded.sfx_peak_db,
        "music_lufs": loaded.music_lufs,
        "has_render_script": bool(loaded.music.get("render_script")),
        "code_art": loaded.code_art,
        "sprites": {k: v for k, v in loaded.sprites.items() if k != "_bad"},
        "engines": {name: engines.status(e) for name, e in engines.ENGINES.items()},
        "problems": manifest.validate(loaded, check_files=False),
        "assets": [asset_json(loaded, a) for a in loaded.assets],
    }


def find(loaded: manifest.Manifest, asset_id: str) -> manifest.Asset:
    for a in loaded.assets:
        if a.id == asset_id:
            return a
    raise UserError(f"{asset_id!r} is not in {loaded.path.name}")


def mark_draft(loaded: manifest.Manifest, a: manifest.Asset) -> bool:
    """A freshly made file moves a todo asset to draft (done stays the user's call)."""
    if a.status == "todo":
        manifest.set_status(loaded.path, a.id, "draft")
        return True
    return False


def sound_info(path: Path) -> dict:
    info = audio.describe(audio.read(path))
    return {"seconds": round(info.seconds, 2), "peak_db": round(info.peak_db, 1), "rms_db": round(info.rms_db, 1),
            "attack_ms": round(info.attack_ms), "brightness": round(info.brightness),
            "shape": [round(v, 3) for v in info.envelope]}


def music_info(path: Path) -> dict:
    info = music.describe(path)
    return {"seconds": round(info.seconds, 1), "lufs": None if info.lufs is None else round(info.lufs, 1),
            "true_peak": None if info.true_peak is None else round(info.true_peak, 1), "exact": info.exact,
            "seam_jump": round(info.seam_jump, 3), "edge_motion": round(info.edge_motion, 3),
            "silent_head": round(info.silent_head, 2), "silent_tail": round(info.silent_tail, 2)}


# --- sound takes (sfxr variants to listen to) ----------------------------------------------------

def takes_dir(loaded: manifest.Manifest, a: manifest.Asset) -> Path:
    return pipeline.sfx_source(loaded, a).parent / "variants"


def take_number(path: Path, asset_id: str) -> int:
    found = re.fullmatch(re.escape(asset_id) + r"_(\d+)", path.stem)
    return int(found.group(1)) if found else 0


def list_takes(loaded: manifest.Manifest, a: manifest.Asset) -> list[dict]:
    folder = takes_dir(loaded, a)
    wavs = sorted(folder.glob(f"{a.id}_*.wav"), key=lambda p: take_number(p, a.id)) if folder.exists() else []
    takes = []
    for wav in wavs:
        if not take_number(wav, a.id):
            continue
        params = wav.with_suffix(".yaml")
        note = ""
        if params.exists():
            first = params.read_text(encoding="utf-8").split("\n# made: ", 1)
            note = first[1].strip() if len(first) > 1 else ""
        takes.append({"name": wav.stem, "url": file_url(loaded.root, wav), "info": sound_info(wav), "note": note})
    return takes


def make_takes(loaded: manifest.Manifest, a: manifest.Asset, preset: str = "", count: int = 3,
               base_take: str = "", word: str = "", amount: float = 0.05) -> list[str]:
    """New takes in sounds/variants/<id>_<n>: fresh seeds of a preset, a tweak of one sound (the
    current one or a take) or small random changes to it. Returns the new take names."""
    src = pipeline.sfx_source(loaded, a)
    folder = takes_dir(loaded, a)
    if base_take:
        base_path = folder / f"{base_take}.yaml"
        if not take_number(base_path, a.id) or not base_path.exists():
            raise UserError(f"no take called {base_take}")
    else:
        base_path = src
    if not preset and not base_path.exists():
        raise UserError(f"{a.id} has no sound yet: start from a preset")
    base = sfxr.load(base_path) if not preset else None
    existing = [take_number(p, a.id) for p in folder.glob(f"{a.id}_*.yaml")] if folder.exists() else []
    first = max(existing, default=0) + 1
    made = []
    for n in range(first, first + (1 if word else max(1, min(count, 12)))):
        if preset:
            seed = random.randrange(1, 100000)
            params, label, note = sfxr.preset(preset, seed), preset, f"{preset}, seed {seed}"
        elif word:
            params, label = sfxr.tweak(base, word), ""
            note = f"{base_take or 'current sound'}, {word}"
        else:
            seed = random.randrange(1, 100000)
            params, label = sfxr.mutate(base, seed=seed, amount=amount), ""
            note = f"like {base_take or 'the current sound'}"
        stem = folder / f"{a.id}_{n}"
        sfxr.save(stem.with_suffix(".yaml"), params, label)
        with open(stem.with_suffix(".yaml"), "a", encoding="utf-8") as f:
            f.write(f"\n# made: {note}\n")
        audio.write_wav(stem.with_suffix(".wav"), audio.clean(sfxr.render(params), peak_db=loaded.sfx_peak_db))
        made.append(stem.name)
    return made


def keep_take(loaded: manifest.Manifest, a: manifest.Asset, take: str) -> list[str]:
    """Makes a take the asset's sound: its parameters become sounds/<id>.yaml and the WAV is rendered."""
    path = takes_dir(loaded, a) / f"{take}.yaml"
    if not take_number(path, a.id) or not path.exists():
        raise UserError(f"no take called {take}")
    params = sfxr.load(path)
    sfxr.save(pipeline.sfx_source(loaded, a), params, "")
    problems = pipeline.make_sfx(loaded, a)
    mark_draft(loaded, a)
    return problems


def clear_takes(loaded: manifest.Manifest, a: manifest.Asset) -> int:
    folder = takes_dir(loaded, a)
    removed = 0
    for path in list(folder.glob(f"{a.id}_*")) if folder.exists() else []:
        if take_number(path, a.id) and path.suffix in (".wav", ".yaml"):
            path.unlink()
            removed += 1
    if folder.exists() and not any(folder.iterdir()):
        folder.rmdir()
    return removed // 2


# --- uploads (files dropped on the page) ----------------------------------------------------------

def upload_path(name: str) -> Path:
    """An uploaded file by the name the server gave it; only plain names inside UPLOADS."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise UserError("unknown upload")
    path = UPLOADS / name
    if not path.is_file():
        raise UserError("that upload is gone; drop the file again")
    return path


def save_upload(name: str, data: bytes) -> str:
    UPLOADS.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._") or "file"
    stored = f"{int(time.time() * 1000)}_{safe}"
    (UPLOADS / stored).write_bytes(data)
    return stored


# --- actions -------------------------------------------------------------------------------------

def _number(body: dict, key: str) -> float | None:
    value = body.get(key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise UserError(f"{key} must be a number") from None


def do_status(loaded: manifest.Manifest, body: dict) -> dict:
    a = find(loaded, str(body.get("id", "")))
    manifest.set_status(loaded.path, a.id, str(body.get("status", "")))
    return {"message": f"{a.id} is now {body.get('status')}"}


def do_validate(loaded: manifest.Manifest, body: dict) -> dict:
    problems = manifest.validate(loaded)
    if loaded.palette:
        try:
            palette.load(loaded.root / loaded.palette)
        except palette.PaletteError as error:
            problems.append(f"palette: {error}")
    return {"problems": problems, "message": f"{len(problems) or 'no'} problem{'s' if len(problems) != 1 else ''}"}


def do_check(loaded: manifest.Manifest, body: dict) -> dict:
    colors = [e.color for e in pipeline.palette_entries(loaded)]
    ids = body.get("ids") or []
    assets = [find(loaded, i) for i in ids] if ids else [
        a for a in loaded.assets if loaded.asset_path(a).exists() and a.kind != "music"]
    problems = []
    for a in assets:
        try:
            problems += pipeline.check(loaded, a, colors)
        except KNOWN_ERRORS as error:
            problems.append(f"{a.id}: {error}")
    return {"problems": problems, "message": f"checked {len(assets)}: {len(problems) or 'no'} problems"}


def do_credits(loaded: manifest.Manifest, body: dict) -> dict:
    out = loaded.root / "CREDITS.md"
    out.write_text(credits.render(loaded), encoding="utf-8")
    return {"message": "wrote CREDITS.md"}


def do_open_folder(loaded: manifest.Manifest, body: dict) -> dict:
    open_path(loaded.root)
    return {"message": ""}


def do_info(loaded: manifest.Manifest, body: dict) -> dict:
    a = find(loaded, str(body.get("id", "")))
    path = loaded.asset_path(a)
    if not path.exists():
        return {"info": None, "problems": []}
    info = music_info(path) if path.suffix.lower() == ".ogg" else sound_info(path)
    problems = pipeline.check(loaded, a, [])
    return {"info": info, "problems": problems}


def do_takes(loaded: manifest.Manifest, body: dict) -> dict:
    a = find(loaded, str(body.get("id", "")))
    current = loaded.asset_path(a)
    sound = {"url": file_url(loaded.root, current), "info": sound_info(current)} if current.exists() else None
    return {"takes": list_takes(loaded, a), "current": sound,
            "has_params": pipeline.sfx_source(loaded, a).exists() if a.source == "sfxr" else False}


def do_make_takes(loaded: manifest.Manifest, body: dict) -> dict:
    a = find(loaded, str(body.get("id", "")))
    preset = str(body.get("preset") or "")
    if preset and preset not in sfxr.PRESETS:
        raise UserError(f"unknown preset {preset}")
    word = str(body.get("tweak") or "")
    made = make_takes(loaded, a, preset=preset, count=int(body.get("count") or 3),
                      base_take=str(body.get("from") or ""), word=word,
                      amount=_number(body, "amount") or 0.05)
    return {"made": made, "message": f"made {len(made)} take{'s' if len(made) != 1 else ''}"}


def do_keep(loaded: manifest.Manifest, body: dict) -> dict:
    a = find(loaded, str(body.get("id", "")))
    problems = keep_take(loaded, a, str(body.get("take", "")))
    return {"problems": problems, "message": f"{a.id} now uses {body.get('take')}"}


def do_clear_takes(loaded: manifest.Manifest, body: dict) -> dict:
    a = find(loaded, str(body.get("id", "")))
    return {"message": f"removed {clear_takes(loaded, a)} takes"}


def _overwrite_guard(path: Path, body: dict) -> None:
    if path.exists() and not body.get("force"):
        raise UserError("REPLACE?")  # the page asks the user, then sends force


def do_import_sound(loaded: manifest.Manifest, body: dict) -> dict:
    a = find(loaded, str(body.get("id", "")))
    out = loaded.asset_path(a)
    _overwrite_guard(out, body)
    source = upload_path(str(body.get("upload", "")))
    match = upload_path(str(body["match"])) if body.get("match") else None
    problems = pipeline.clean_into(loaded, a, source, do_trim=bool(body.get("trim", True)),
                                   match=match, max_seconds=_number(body, "max_seconds"))
    mark_draft(loaded, a)
    note = " Record its license in assets.yaml." if a.source in manifest.LICENSED_SOURCES and not a.license else ""
    return {"problems": problems, "message": f"{a.id}: imported.{note}"}


def do_import_music(loaded: manifest.Manifest, body: dict) -> dict:
    a = find(loaded, str(body.get("id", "")))
    out = loaded.asset_path(a)
    if out.suffix.lower() != ".ogg":
        raise UserError(f"{a.id}: music files are .ogg, but file is {a.file}")
    _overwrite_guard(out, body)
    source = upload_path(str(body.get("upload", "")))
    lufs = _number(body, "loudness")
    if lufs is None:
        lufs = loaded.music_lufs if loaded.music_lufs is not None else -16.0
    note = music.encode_ogg(source, out, None if body.get("keep_level") else lufs,
                            start=_number(body, "start"), end=_number(body, "end"))
    mark_draft(loaded, a)
    problems = pipeline.check_ogg(loaded, a)
    return {"problems": problems, "message": f"{a.id}: imported. {note}".strip()}


def do_render_music(loaded: manifest.Manifest, body: dict) -> dict:
    assets = pipeline.music_assets(loaded, list(body.get("ids") or []))
    if not assets:
        raise UserError("no source: synth music in the manifest")
    results = pipeline.render_music(loaded, assets, music.find_godot(), None)
    problems = []
    for a, found, note in results:
        mark_draft(loaded, a)
        problems += found
    return {"problems": problems, "message": f"rendered {len(results)} track{'s' if len(results) != 1 else ''}"}


def do_draw(loaded: manifest.Manifest, body: dict) -> dict:
    a = find(loaded, str(body.get("id", "")))
    problems = pipeline.draw(loaded, a)
    mark_draft(loaded, a)
    return {"problems": problems, "message": f"{a.id}: drawn"}


def do_export(loaded: manifest.Manifest, body: dict) -> dict:
    a = find(loaded, str(body.get("id", "")))
    problems = pipeline.export(loaded, a)
    mark_draft(loaded, a)
    return {"problems": problems, "message": f"{a.id}: exported"}


# --- background jobs (AI engines: loading a model or making a picture takes seconds to minutes) -------

class Job:
    def __init__(self, label: str) -> None:
        self.id = f"{time.time():.3f}"
        self.label = label
        self.step = ""
        self.state = "running"        # running | done | error | cancelled
        self.error = ""
        self.result: dict = {}
        self.started = time.time()
        self.finished = 0.0
        self.cancel = False

    def json(self) -> dict:
        end = self.finished or time.time()
        return {"id": self.id, "label": self.label, "step": self.step, "state": self.state, "error": self.error,
                "result": self.result, "seconds": round(end - self.started)}


JOB_LOCK = threading.Lock()
CURRENT: dict[str, Job | None] = {"job": None}


def start_job(label: str, work: Callable[[Job], dict]) -> Job:
    """Runs `work` on its own thread; only one job at a time (they share the graphics card)."""
    with JOB_LOCK:
        running = CURRENT["job"]
        if running is not None and running.state == "running":
            raise UserError(f"still busy: {running.label}")
        job = Job(label)
        CURRENT["job"] = job

    def run() -> None:
        try:
            job.result = work(job) or {}
            job.state = "cancelled" if job.cancel else "done"
        except Exception as error:
            job.state = "cancelled" if job.cancel else "error"
            job.error = "" if job.cancel else str(error)
            if not job.cancel and not isinstance(error, (UserError, engines.EngineError, *KNOWN_ERRORS)):
                traceback.print_exc()
        job.finished = time.time()

    threading.Thread(target=run, daemon=True).start()
    return job


def do_job(loaded: manifest.Manifest, body: dict) -> dict:
    job = CURRENT["job"]
    return {"job": job.json() if job else None}


def do_cancel(loaded: manifest.Manifest, body: dict) -> dict:
    job = CURRENT["job"]
    if job is not None and job.state == "running":
        job.cancel = True
        engines.stop_all()  # stops the model mid-picture; it loads again next time
    return {"message": "stopped"}


def do_engine_setup(loaded: manifest.Manifest, body: dict) -> dict:
    engine = engines.get(str(body.get("name", "")))

    def work(job: Job) -> dict:
        for line in engines.setup(engine.name):
            job.step = line
            if job.cancel:
                raise UserError("stopped")
        return {"message": f"the {engine.title.lower()} engine is ready"}

    start_job(f"Setting up the {engine.title.lower()} engine", work)
    return {"message": ""}


# --- pictures -----------------------------------------------------------------------------------------

def do_pictures(loaded: manifest.Manifest, body: dict) -> dict:
    items = []
    for item in pictures.list_all(loaded):
        path = pictures.folder(loaded) / item["name"]
        items.append(item | {"url": file_url(loaded.root, path)})
    return {"pictures": items, "engine": engines.status(engines.get("picture"))}


def _clamp(body: dict, key: str, default: int, low: int, high: int) -> int:
    value = _number(body, key)
    return default if value is None else max(low, min(high, int(value)))


def do_make_pictures(loaded: manifest.Manifest, body: dict) -> dict:
    prompt = str(body.get("prompt", "")).strip()
    if not prompt:
        raise UserError("describe the picture first")
    engine = engines.get("picture")
    if not engines.is_installed(engine):
        raise UserError("the picture engine isn't set up yet: press Set up on the Pictures tab")
    takes = _clamp(body, "takes", 1, 1, 8)
    width, height = _clamp(body, "width", 1024, 256, 1536), _clamp(body, "height", 1024, 256, 1536)
    steps = _clamp(body, "steps", 4, 1, 12)
    fixed_seed = _number(body, "seed")
    refs = [str(pictures.path_of(loaded, pictures.original_of(loaded, name))) for name in body.get("refs") or []]
    request = {"prompt": prompt, "width": width, "height": height, "steps": steps, "tile": bool(body.get("tile")),
               "refs": refs, "for": str(body.get("for") or "")}

    def work(job: Job) -> dict:
        made = []
        for take in range(takes):
            if job.cancel:
                break
            seed = int(fixed_seed) + take if fixed_seed is not None else random.randrange(1, 2**31 - 1)
            out = pictures.new_path(loaded, request["for"] or prompt, seed)
            label = f"picture {take + 1} of {takes}: " if takes > 1 else ""

            def on_step(text: str) -> None:
                job.step = label + text

            answer = engines.worker("picture").ask(request | {"out": str(out), "seed": seed}, on_step)
            pictures.record(out, request | {"steps": steps}, answer)
            made.append(out.name)
        return {"made": made, "message": f"made {len(made)} picture{'s' if len(made) != 1 else ''}"}

    start_job("Pictures", work)
    return {"message": ""}


def _chosen_frames(body: dict) -> dict[str, str]:
    frames = body.get("frames") or {}
    if not isinstance(frames, dict):
        raise UserError("frames: {frame: picture}")
    return {str(k): str(v) for k, v in frames.items() if v}


def do_make_frames(loaded: manifest.Manifest, body: dict) -> dict:
    """Pictures for an asset's missing frames, each made from one base picture with its own pose words, then cut
    out (if the cut-out engine is set up)."""
    a = find(loaded, str(body.get("id", "")))
    # the picture model reads colors, not transparency or 12 px sprites: work from the full-size original
    base = pictures.path_of(loaded, pictures.original_of(loaded, str(body.get("name", ""))))
    base_meta = pictures.read_meta(base)
    poses = {str(k): str(v).strip() for k, v in (body.get("poses") or {}).items() if str(v).strip()}
    targets = pictures.frame_targets(loaded, a)
    if not poses:
        raise UserError("no frames to make: every frame has a picture already")
    if any(frame not in targets for frame in poses):
        raise UserError(f"{a.id} has frames: {', '.join(targets)}")
    if not engines.is_installed(engines.get("picture")):
        raise UserError("the picture engine isn't set up yet: press Set up on the Pictures tab")
    cut = engines.is_installed(engines.get("cutout"))
    with Image.open(base) as image:
        width, height = image.size

    def work(job: Job) -> dict:
        made = {}
        for n, (frame, words) in enumerate(poses.items()):
            if job.cancel:
                break
            label = f"frame {n + 1} of {len(poses)} ({frame}): "

            def on_step(text: str) -> None:
                job.step = label + text

            seed = random.randrange(1, 2**31 - 1)
            out = pictures.new_path(loaded, frame, seed)
            request = {"prompt": words, "width": width, "height": height, "steps": int(base_meta.get("steps") or 4),
                       "tile": False, "refs": [str(base)], "for": a.id, "frame": frame}
            answer = engines.worker("picture").ask(request | {"out": str(out), "seed": seed}, on_step)
            meta = pictures.record(out, request, answer)
            made_name = out.name
            if cut:
                cut_out = pictures.cutout_path(loaded, out.name)
                engines.worker("cutout").ask({"in": str(out), "out": str(cut_out)}, on_step)
                pictures.record_cutout(cut_out, out.name, meta)
                made_name = cut_out.name
            made[frame] = made_name
        return {"made": list(made.values()), "frames": made,
                "message": f"made {len(made)} frame{'s' if len(made) != 1 else ''} for {a.id}"}

    start_job("Frames", work)
    return {"message": ""}


def do_animation_preview(loaded: manifest.Manifest, body: dict) -> dict:
    """The frames as Use all frames would save them (one shared crop), as PNG data URLs; nothing saved."""
    a = find(loaded, str(body.get("id", "")))
    sprites = pictures.make_frames(loaded, a, _chosen_frames(body), background=bool(body.get("background", True)),
                                   snap=bool(body.get("snap", True)), outline=bool(body.get("outline", True)))
    frames = {}
    for frame, sprite in sprites.items():
        buffer = io.BytesIO()
        sprite.save(buffer, "PNG")
        frames[frame] = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    return {"frames": frames, "width": a.size[0], "height": a.size[1]}


def do_animation_use(loaded: manifest.Manifest, body: dict) -> dict:
    a = find(loaded, str(body.get("id", "")))
    chosen = _chosen_frames(body)
    paths = {path.stem: path for _, _, path in loaded.frame_paths(a)}
    if any(paths.get(frame) and paths[frame].exists() for frame in chosen):
        _overwrite_guard(next(paths[f] for f in chosen if paths.get(f) and paths[f].exists()), body)
    problems = pictures.use_frames(loaded, a, chosen, background=bool(body.get("background", True)),
                                   snap=bool(body.get("snap", True)), outline=bool(body.get("outline", True)))
    manifest.set_fields(loaded.path, a.id, {"source": "ai"} | ({"status": "draft"} if a.status == "todo" else {}))
    return {"problems": problems, "message": f"{a.id}: saved {len(chosen)} frame{'s' if len(chosen) != 1 else ''} (source: ai)"}


def do_save_sprite(loaded: manifest.Manifest, body: dict) -> dict:
    """Make sprite: a picture's game-sized sprite kept in pictures/ as a picture of its own."""
    a = find(loaded, str(body.get("id", "")))
    path = pictures.save_sprite(loaded, a, str(body.get("name", "")), bool(body.get("background", True)),
                                bool(body.get("snap", True)), bool(body.get("outline", True)), str(body.get("frame") or ""))
    return {"made": [path.name], "message": f"kept {path.name} in pictures/ ({a.id})"}


def do_touchup(loaded: manifest.Manifest, body: dict) -> dict:
    """Touch up with Claude: game-sized drafts kept in pictures/ with their text rows, for Claude to fix.
    Nothing goes into the game until one is used."""
    a = find(loaded, str(body.get("id", "")))
    try:
        saved = touchup.drafts(loaded, a, _chosen_frames(body), bool(body.get("background", True)),
                               bool(body.get("snap", True)), bool(body.get("outline", True)), bool(body.get("every_frame")))
    except touchup.TouchUpError as error:
        raise UserError(str(error)) from None
    count = f"{len(saved)} touch-up draft{'s' if len(saved) != 1 else ''}"
    return {"made": [p.name for p in saved],
            "message": f'{a.id}: {count} in your pictures. Ask Claude: "touch up the {a.id} drafts". '
                       "Press Use on one when you like it."}


def do_cutout_picture(loaded: manifest.Manifest, body: dict) -> dict:
    """A copy of a picture with its background made transparent (cut-out engine, on the processor)."""
    name = str(body.get("name", ""))
    source = pictures.path_of(loaded, name)
    if not engines.is_installed(engines.get("cutout")):
        raise UserError("the cut-out engine isn't set up yet: press Set up next to Cut out on the Pictures tab")

    def work(job: Job) -> dict:
        def on_step(text: str) -> None:
            job.step = text

        out = pictures.cutout_path(loaded, name)
        engines.worker("cutout").ask({"in": str(source), "out": str(out)}, on_step)
        pictures.record_cutout(out, name, pictures.read_meta(source))
        return {"made": [out.name], "message": f"cut out {name} -> {out.name}"}

    start_job("Cut-out", work)
    return {"message": ""}


def do_keep_picture(loaded: manifest.Manifest, body: dict) -> dict:
    pictures.keep(loaded, str(body.get("name", "")), bool(body.get("kept", True)))
    return {"message": ""}


def do_remove_picture(loaded: manifest.Manifest, body: dict) -> dict:
    pictures.remove(loaded, str(body.get("name", "")))
    return {"message": "moved to pictures/_removed"}


def do_use_picture(loaded: manifest.Manifest, body: dict) -> dict:
    """A picture becomes an image asset's file: background removed, shrunk, snapped to the palette."""
    a = find(loaded, str(body.get("id", "")))
    frame = str(body.get("frame") or "")
    frames = {path.stem: path for _, _, path in loaded.frame_paths(a)}
    _overwrite_guard(frames.get(frame, loaded.asset_path(a)), body)
    problems = pictures.use_as_asset(loaded, a, str(body.get("name", "")), background=bool(body.get("background", True)),
                                     snap=bool(body.get("snap", True)), outline=bool(body.get("outline", True)),
                                     frame=frame)
    changes = {"source": "ai"} | ({"status": "draft"} if a.status == "todo" else {})
    manifest.set_fields(loaded.path, a.id, changes)
    return {"problems": problems, "message": f"{frame or a.id} now uses {body.get('name')} (source: ai)"}


def do_preview_picture(loaded: manifest.Manifest, body: dict) -> dict:
    """What Use would make, without saving: the sprite as a PNG data URL, at its real size."""
    a = find(loaded, str(body.get("id", "")))
    sprite = pictures.make_sprite(loaded, a, str(body.get("name", "")), background=bool(body.get("background", True)),
                                  snap=bool(body.get("snap", True)), outline=bool(body.get("outline", True)))
    buffer = io.BytesIO()
    sprite.save(buffer, "PNG")
    return {"image": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii"),
            "width": sprite.width, "height": sprite.height}


# --- AI music takes -----------------------------------------------------------------------------------

def do_music_takes(loaded: manifest.Manifest, body: dict) -> dict:
    items = [item | {"url": file_url(loaded.root, made.folder(loaded, "music") / item["name"])}
             for item in made.list_all(loaded, "music")]
    return {"takes": items, "engine": engines.status(engines.get("music"))}


def do_make_music(loaded: manifest.Manifest, body: dict) -> dict:
    prompt = str(body.get("prompt", "")).strip()
    if not prompt:
        raise UserError("describe the music first")
    if not engines.is_installed(engines.get("music")):
        raise UserError("the music engine isn't set up yet: press Set up on the Music tab")
    takes = _clamp(body, "takes", 1, 1, 6)
    bpm = _number(body, "bpm")
    lyrics = str(body.get("lyrics", "")).strip()
    request = {"prompt": prompt, "seconds": _clamp(body, "seconds", 60, 10, 300),
               "bpm": int(bpm) if bpm and 30 <= bpm <= 300 else None, "key": str(body.get("key", "")).strip(),
               "lyrics": lyrics, "instrumental": not lyrics, "steps": _clamp(body, "steps", 8, 4, 20),
               "planner": bool(body.get("planner"))}
    fixed_seed = _number(body, "seed")

    def work(job: Job) -> dict:
        done = []
        for take in range(takes):
            if job.cancel:
                break
            seed = int(fixed_seed) + take if fixed_seed is not None else random.randrange(1, 2**31 - 1)
            out = made.new_path(loaded, "music", prompt, seed)
            label = f"take {take + 1} of {takes}: " if takes > 1 else ""

            def on_step(text: str) -> None:
                job.step = label + text

            answer = engines.worker("music").ask(request | {"out": str(out), "seed": seed}, on_step)
            made.record(out, request | {"seed": answer.get("seed", seed), "model": "ACE-Step 1.5 turbo"})
            done.append(out.name)
        return {"made": done, "message": f"made {len(done)} take{'s' if len(done) != 1 else ''}"}

    start_job("Music", work)
    return {"message": ""}


def do_keep_music(loaded: manifest.Manifest, body: dict) -> dict:
    made.keep(loaded, "music", str(body.get("name", "")), bool(body.get("kept", True)))
    return {"message": ""}


def do_remove_music(loaded: manifest.Manifest, body: dict) -> dict:
    made.remove(loaded, "music", str(body.get("name", "")))
    return {"message": "moved to music-takes/_removed"}


def do_use_music(loaded: manifest.Manifest, body: dict) -> dict:
    """A take becomes a music asset's OGG: cut to the chosen loop, at the game's loudness."""
    a = find(loaded, str(body.get("id", "")))
    out = loaded.asset_path(a)
    if a.kind != "music" or out.suffix.lower() != ".ogg":
        raise UserError(f"{a.id} isn't a music asset with an .ogg file")
    _overwrite_guard(out, body)
    source = made.path_of(loaded, "music", str(body.get("name", "")))
    lufs = _number(body, "loudness")
    if lufs is None:
        lufs = loaded.music_lufs if loaded.music_lufs is not None else -16.0
    note = music.encode_ogg(source, out, None if body.get("keep_level") else lufs,
                            start=_number(body, "start"), end=_number(body, "end"))
    manifest.set_fields(loaded.path, a.id, {"source": "ai"} | ({"status": "draft"} if a.status == "todo" else {}))
    problems = pipeline.check_ogg(loaded, a)
    return {"problems": problems, "message": f"{a.id} now uses {body.get('name')} (source: ai). {note}".strip()}


# --- AI sound and voice takes (shared: list, keep, remove, use) -----------------------------------------

def _take_kind(body: dict) -> str:
    kind = str(body.get("kind", ""))
    if kind not in ("sound", "voice"):
        raise UserError("kind must be sound or voice")
    return kind


def do_takes_list(loaded: manifest.Manifest, body: dict) -> dict:
    kind = _take_kind(body)
    items = [item | {"url": file_url(loaded.root, made.folder(loaded, kind) / item["name"])}
             for item in made.list_all(loaded, kind)]
    return {"takes": items, "engine": engines.status(engines.get(kind))}


def do_takes_keep(loaded: manifest.Manifest, body: dict) -> dict:
    made.keep(loaded, _take_kind(body), str(body.get("name", "")), bool(body.get("kept", True)))
    return {"message": ""}


def do_takes_remove(loaded: manifest.Manifest, body: dict) -> dict:
    kind = _take_kind(body)
    made.remove(loaded, kind, str(body.get("name", "")))
    return {"message": f"moved to {made.KINDS[kind][0]}/_removed"}


def do_takes_use(loaded: manifest.Manifest, body: dict) -> dict:
    """A sound or voice take becomes a .wav asset: mono 16-bit, trimmed (not for loops), at the game's peak
    level or matched to the sound it replaces."""
    kind = _take_kind(body)
    a = find(loaded, str(body.get("id", "")))
    out = loaded.asset_path(a)
    if out.suffix.lower() != ".wav":
        raise UserError(f"{a.id}'s file is {a.file}; sounds and voices become .wav assets")
    _overwrite_guard(out, body)
    source = made.path_of(loaded, kind, str(body.get("name", "")))
    loop = bool(made.read_meta(source).get("loop"))
    match = upload_path(str(body["match"])) if body.get("match") else None
    problems = pipeline.clean_into(loaded, a, source, do_trim=not loop, match=match,
                                   max_seconds=_number(body, "max_seconds"))
    manifest.set_fields(loaded.path, a.id, {"source": "ai"} | ({"status": "draft"} if a.status == "todo" else {}))
    return {"problems": problems, "message": f"{a.id} now uses {source.name} (source: ai)"}


def _make_takes(loaded: manifest.Manifest, kind: str, label: str, request: dict, takes: int,
                fixed_seed: float | None, describe: str) -> dict:
    if not engines.is_installed(engines.get(kind)):
        raise UserError(f"the {kind} engine isn't set up yet: press Set up on its tab")

    def work(job: Job) -> dict:
        done = []
        for take in range(takes):
            if job.cancel:
                break
            seed = int(fixed_seed) + take if fixed_seed is not None else random.randrange(1, 2**31 - 1)
            out = made.new_path(loaded, kind, describe, seed)
            prefix = f"take {take + 1} of {takes}: " if takes > 1 else ""

            def on_step(text: str) -> None:
                job.step = prefix + text

            answer = engines.worker(kind).ask(request | {"out": str(out), "seed": seed}, on_step)
            made.record(out, request | {"seed": answer.get("seed", seed), "seconds": answer.get("seconds")})
            done.append(out.name)
        return {"made": done, "message": f"made {len(done)} take{'s' if len(done) != 1 else ''}"}

    start_job(label, work)
    return {"message": ""}


def do_make_sounds(loaded: manifest.Manifest, body: dict) -> dict:
    prompt = str(body.get("prompt", "")).strip()
    if not prompt:
        raise UserError("describe the sound first")
    seconds = _number(body, "seconds") or 2.0
    request = {"prompt": prompt, "seconds": max(0.5, min(30.0, seconds)), "steps": _clamp(body, "steps", 8, 4, 50),
               "mono": bool(body.get("mono", True)), "loop": bool(body.get("loop")), "model": "Stable Audio 3 Small SFX"}
    return _make_takes(loaded, "sound", "Sounds", request, _clamp(body, "takes", 3, 1, 8), _number(body, "seed"), prompt)


def do_make_voices(loaded: manifest.Manifest, body: dict) -> dict:
    text = str(body.get("text", "")).strip()
    if not text:
        raise UserError("write the words to say first")
    if len(text) > 1500:
        raise UserError("up to 1,500 characters a reading; split longer text")
    request = {"text": text, "who": str(body.get("who", "")).strip(), "tone": str(body.get("tone", "")).strip(),
               "language": str(body.get("language", "") or "English"), "model": "Qwen3-TTS 1.7B VoiceDesign"}
    return _make_takes(loaded, "voice", "Voices", request, _clamp(body, "takes", 2, 1, 6), _number(body, "seed"), text)


POST: dict[str, Callable[[manifest.Manifest, dict], dict]] = {
    "/api/takes": do_takes_list, "/api/takes/keep": do_takes_keep, "/api/takes/remove": do_takes_remove,
    "/api/takes/use": do_takes_use, "/api/sounds/make": do_make_sounds, "/api/voices/make": do_make_voices,
    "/api/musictakes": do_music_takes, "/api/musictakes/make": do_make_music, "/api/musictakes/keep": do_keep_music,
    "/api/musictakes/remove": do_remove_music, "/api/musictakes/use": do_use_music,
    "/api/job": do_job, "/api/cancel": do_cancel, "/api/engines/setup": do_engine_setup,
    "/api/pictures": do_pictures, "/api/pictures/make": do_make_pictures, "/api/pictures/keep": do_keep_picture,
    "/api/pictures/remove": do_remove_picture,
    "/api/pictures/preview": do_preview_picture,
    "/api/pictures/frames": do_make_frames, "/api/pictures/animation": do_animation_preview,
    "/api/pictures/animation/use": do_animation_use, "/api/touchup": do_touchup,
    "/api/pictures/sprite": do_save_sprite,
    "/api/pictures/cutout": do_cutout_picture, "/api/pictures/use": do_use_picture,
    "/api/status": do_status, "/api/validate": do_validate, "/api/check": do_check, "/api/credits": do_credits,
    "/api/open-folder": do_open_folder, "/api/info": do_info,
    "/api/sfx/takes": do_takes, "/api/sfx/make": do_make_takes, "/api/sfx/keep": do_keep,
    "/api/sfx/clear": do_clear_takes, "/api/sfx/import": do_import_sound,
    "/api/music/import": do_import_music, "/api/music/render": do_render_music,
    "/api/art/draw": do_draw, "/api/art/export": do_export,
}
# these don't wait for a running action (jobs run in the background and only take the job slot)
READ_ONLY = {"/api/info", "/api/sfx/takes", "/api/validate", "/api/job", "/api/cancel", "/api/pictures",
             "/api/engines/setup", "/api/pictures/make", "/api/musictakes", "/api/musictakes/make", "/api/takes",
             "/api/sounds/make", "/api/voices/make", "/api/pictures/cutout",
             "/api/pictures/preview", "/api/pictures/frames", "/api/pictures/animation"}


# --- the server ------------------------------------------------------------------------------------

def make_handler(manifest_path: Path) -> type[BaseHTTPRequestHandler]:
    busy = {"what": ""}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # keep the console quiet
            pass

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data: dict) -> None:
            self._send(code, json.dumps(data).encode("utf-8"), "application/json")

        def _local_only(self) -> bool:
            """Only this PC's own page: other websites can't call these routes (DNS rebinding, forged posts)."""
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("127.0.0.1", "localhost"):
                self._json(403, {"error": "gamekit only answers http://127.0.0.1"})
                return False
            return True

        def do_GET(self) -> None:
            if not self._local_only():
                return
            url = urlparse(self.path)
            try:
                if url.path == "/":
                    self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
                elif url.path == "/api/state":
                    self._json(200, state(manifest.load(manifest_path)) | {"busy": busy["what"]})
                elif url.path.startswith("/file/"):
                    self._file(unquote(url.path[len("/file/"):]))
                elif url.path.startswith("/preview/"):
                    self._preview(unquote(url.path[len("/preview/"):]))
                else:
                    self._json(404, {"error": "not found"})
            except (UserError, *KNOWN_ERRORS) as error:
                self._json(400, {"error": str(error)})
            except Exception as error:
                traceback.print_exc()
                self._json(500, {"error": f"{type(error).__name__}: {error}"})

        def _file(self, rel: str) -> None:
            root = manifest_path.parent.resolve()
            path = (root / rel).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                self._json(404, {"error": "not found"})
                return
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self._send(200, path.read_bytes(), content_type)

        def _preview(self, asset_id: str) -> None:
            loaded = manifest.load(manifest_path)
            asset = find(loaded, asset_id)
            items = pipeline.preview_items(loaded, [asset])
            image = items[0][1] if items else codeart.render(loaded, asset)  # a file wins over code art
            if image is None:
                self._json(404, {"error": "no image yet"})
                return
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            self._send(200, buffer.getvalue(), "image/png")

        def do_POST(self) -> None:
            if not self._local_only():
                return
            if self.headers.get("X-Gamekit") != "1":  # a header other sites' pages can't send without asking first
                self._json(403, {"error": "missing X-Gamekit header"})
                return
            url = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_UPLOAD:
                self._json(413, {"error": "file too big"})
                return
            data = self.rfile.read(length) if length else b""
            if url.path == "/api/upload":
                name = parse_qs(url.query).get("name", ["file"])[0]
                self._json(200, {"upload": save_upload(name, data)})
                return
            handler = POST.get(url.path)
            if handler is None:
                self._json(404, {"error": "not found"})
                return
            try:
                body = json.loads(data or b"{}")
                if not isinstance(body, dict):
                    raise UserError("expected a JSON object")
            except json.JSONDecodeError:
                self._json(400, {"error": "bad JSON"})
                return
            if url.path in READ_ONLY:
                self._run(handler, body)
                return
            if not ACTION.acquire(blocking=False):
                self._json(409, {"error": f"still busy: {busy['what']}"})
                return
            try:
                busy["what"] = f"{url.path.split('/', 2)[-1]} {body.get('id', '')}".strip()
                self._run(handler, body)
            finally:
                busy["what"] = ""
                ACTION.release()

        def _run(self, handler: Callable[[manifest.Manifest, dict], dict], body: dict) -> None:
            try:
                self._json(200, handler(manifest.load(manifest_path), body))
            except (UserError, *KNOWN_ERRORS) as error:
                self._json(400, {"error": str(error)})
            except Exception as error:
                traceback.print_exc()
                self._json(500, {"error": f"{type(error).__name__}: {error}"})

    return Handler


def make_server(manifest_path: Path, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    """The server on the first free port from `port` (0: any free port, for tests)."""
    manifest.load(manifest_path)  # fail early with a clear message if the manifest is missing
    for candidate in ([port] if port == 0 else range(port, port + 10)):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), make_handler(manifest_path.resolve()))
            return server
        except OSError:
            continue
    raise UserError(f"ports {port}-{port + 9} are all in use")


def open_path(path: Path) -> None:
    """Shows a folder in File Explorer (or the system's file manager)."""
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _windows_browsers() -> list[str]:
    places = [os.environ.get(name, "") for name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
    apps = [r"BraveSoftware\Brave-Browser\Application\brave.exe", r"Google\Chrome\Application\chrome.exe",
            r"Microsoft\Edge\Application\msedge.exe"]
    return [str(Path(place) / app) for app in apps for place in places if place]


# Browsers that can show the page as its own window (app mode), in the order they're tried.
BROWSERS = ["brave-browser", "brave", "google-chrome", "chrome", "chromium", "chromium-browser", "msedge"]


def find_browser() -> str | None:
    """A Chromium browser for app mode: $GAMEKIT_BROWSER, then Brave, Chrome or Edge (install folders, then PATH)."""
    configured = os.environ.get("GAMEKIT_BROWSER")
    if configured:
        if Path(configured).exists() or shutil.which(configured):
            return configured
        print(f"  GAMEKIT_BROWSER points to {configured}, which doesn't exist; trying the usual browsers")
    if sys.platform == "win32":
        for path in _windows_browsers():
            if Path(path).exists():
                return path
    for name in BROWSERS:
        found = shutil.which(name)
        if found:
            return found
    return None


def open_window(url: str) -> None:
    """Its own window (app mode) in Brave, Chrome or Edge; otherwise a tab in the default browser."""
    browser = find_browser()
    if browser:
        try:
            subprocess.Popen([browser, f"--app={url}", "--window-size=1280,900"])
            return
        except OSError:
            pass
    import webbrowser
    webbrowser.open(url)


def serve(manifest_path: Path, port: int = DEFAULT_PORT, window: bool = True) -> None:
    server = make_server(manifest_path, port)
    url = f"http://127.0.0.1:{server.server_address[1]}"
    if window:
        threading.Timer(0.8, open_window, args=(url,)).start()
    print(f"\n  gamekit is at {url}  (leave this window open; close it or press Ctrl+C to quit)\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engines.stop_all()
        server.server_close()
        shutil.rmtree(UPLOADS, ignore_errors=True)


def write_launcher(manifest_path: Path, gamekit_script: Path) -> Path:
    """`Start Gamekit.bat` next to the manifest: double-click it to open the page."""
    python = "python" if shutil.which("python") else sys.executable
    bat = manifest_path.resolve().parent / "Start Gamekit.bat"
    bat.write_text(
        "@echo off\r\n"
        "REM Opens gamekit's asset page for this game. Leave this window open while you use it; close it to quit.\r\n"
        "REM Made by `gamekit ui --launcher`; run that again if gamekit moves.\r\n"
        "title Gamekit\r\n"
        'cd /d "%~dp0"\r\n'
        f'"{python}" "{gamekit_script.resolve()}" -m "{manifest_path.name}" ui\r\n'
        "pause\r\n",
        encoding="utf-8", newline="")
    return bat
