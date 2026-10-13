"""`gamekit ui`: a local web page for a game's assets, served on this PC only (127.0.0.1).

The page (plugins/gamekit/ui/index.html) asks this server for JSON and the server does the same work
as the CLI commands. Every request reads assets.yaml again, so edits made by hand or by Claude show
up on the next refresh. One action runs at a time (ACTION); reading state never waits for it.

Adding a tab later (for example an AI generator): a section in index.html plus a handler in GET or POST below.
"""
from __future__ import annotations

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

from . import art, aseprite, audio, codeart, credits, manifest, music, packs, palette, pipeline, sfxr

PAGE = Path(__file__).resolve().parent.parent.parent / "ui" / "index.html"
UPLOADS = Path(tempfile.gettempdir()) / "gamekit-uploads"
DEFAULT_PORT = 7862          # Hearthtone uses 7861
MAX_UPLOAD = 300 * 1024 * 1024
KNOWN_ERRORS = (manifest.ManifestError, palette.PaletteError, art.ArtError, aseprite.AsepriteError,
                packs.PackError, audio.AudioError, music.MusicError, codeart.CodeArtError, ValueError)
ACTION = threading.Lock()
mimetypes.add_type("audio/ogg", ".ogg")
mimetypes.add_type("audio/wav", ".wav")


class UserError(Exception):
    """A problem to show on the page as it is (bad request, unknown asset...)."""


# --- reading the game ------------------------------------------------------------------------

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
    }


def state(loaded: manifest.Manifest) -> dict:
    counts = {s: 0 for s in manifest.STATUSES}
    for a in loaded.assets:
        if a.status in counts:
            counts[a.status] += 1
    return {
        "game": loaded.game or loaded.root.name,
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


POST: dict[str, Callable[[manifest.Manifest, dict], dict]] = {
    "/api/status": do_status, "/api/validate": do_validate, "/api/check": do_check, "/api/credits": do_credits,
    "/api/open-folder": do_open_folder, "/api/info": do_info,
    "/api/sfx/takes": do_takes, "/api/sfx/make": do_make_takes, "/api/sfx/keep": do_keep,
    "/api/sfx/clear": do_clear_takes, "/api/sfx/import": do_import_sound,
    "/api/music/import": do_import_music, "/api/music/render": do_render_music,
    "/api/art/draw": do_draw, "/api/art/export": do_export,
}
READ_ONLY = {"/api/info", "/api/sfx/takes", "/api/validate"}   # these don't wait for a running action


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
