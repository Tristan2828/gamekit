"""Manifest-aware steps: draw, export, check (images, sounds, music), sound and music rendering."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from . import art, aseprite, audio, music, sfxr
from .manifest import KINDS, Asset, Manifest
from .palette import Color, Entry, load_entries


def image_assets(manifest: Manifest, ids: list[str]) -> list[Asset]:
    """The image assets named by `ids` (all of them when empty); unknown ids raise."""
    images = [a for a in manifest.assets if KINDS.get(a.kind, (set(), False))[1] or a.kind == "font"]
    if not ids:
        return images
    by_id = {a.id: a for a in manifest.assets}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise art.ArtError(f"not in the manifest: {', '.join(missing)}")
    return [by_id[i] for i in ids]


def palette_entries(manifest: Manifest) -> list[Entry]:
    if not manifest.palette:
        return []
    return load_entries(manifest.root / manifest.palette)


def draw(manifest: Manifest, asset: Asset) -> list[str]:
    """Renders a Claude-drawn text sprite into the asset's PNG; returns check problems."""
    entries = palette_entries(manifest)
    src = manifest.source_path(asset)
    if src is None or src.suffix.lower() not in (".yaml", ".yml"):
        raise art.ArtError(f"{asset.id}: no text sprite source (set src: art/<id>.yaml or source: claude)")
    sprite = art.load_text_sprite(src, entries)
    image, sidecar = art.render(sprite, where=str(src))
    save_image(manifest, asset, image, sidecar)
    return check(manifest, asset, [e.color for e in entries])


def export(manifest: Manifest, asset: Asset, exe: str | None = None) -> list[str]:
    """Exports the asset's .aseprite file with the Aseprite CLI; returns check problems."""
    src = manifest.source_path(asset)
    if src is None or src.suffix.lower() not in (".aseprite", ".ase"):
        raise aseprite.AsepriteError(f"{asset.id}: no .aseprite source (set src: or source: self)")
    out = manifest.asset_path(asset)
    sidecar = aseprite.export(src, out, exe)
    with Image.open(out) as image:
        save_image(manifest, asset, image.copy(), sidecar)
    return check(manifest, asset, [e.color for e in palette_entries(manifest)])


def save_image(manifest: Manifest, asset: Asset, image: Image.Image, sidecar: dict | None) -> None:
    """Writes an asset's image: a sheet + JSON, or (manifest `frame_files: true`) one PNG per frame."""
    out = manifest.asset_path(asset)
    paths = manifest.frame_paths(asset)
    if not paths or sidecar is None:
        art.save(image, sidecar, out)
        return
    frames = art.split_sheet(image, sidecar)
    for anim, index, path in paths:
        if anim in frames and index < len(frames[anim]):
            path.parent.mkdir(parents=True, exist_ok=True)
            frames[anim][index].save(path)
    stale = art.sidecar_path(out)
    if stale.exists():
        stale.unlink()


def load_frames(manifest: Manifest, asset: Asset) -> dict[str, list[Image.Image]] | None:
    """An asset's frames from frame files (None if it doesn't use them or one is missing)."""
    paths = manifest.frame_paths(asset)
    if not paths or not all(p.exists() for _, _, p in paths):
        return None
    frames: dict[str, list[Image.Image]] = {}
    for anim, _, path in paths:
        with Image.open(path) as image:
            frames.setdefault(anim, []).append(image.convert("RGBA"))
    return frames


def check(manifest: Manifest, asset: Asset, colors: list[Color]) -> list[str]:
    """Problems with an asset's finished PNG: missing file, wrong size or frames, off-palette colors."""
    path = manifest.asset_path(asset)
    if path.suffix.lower() == ".wav":
        return check_wav(manifest, asset)
    if path.suffix.lower() == ".ogg":
        return check_ogg(manifest, asset)
    if path.suffix.lower() != ".png":
        return []
    if not path.exists():
        return [f"{asset.id}: {manifest.output}/{asset.file} doesn't exist yet"]
    problems: list[str] = []
    with Image.open(path) as image:
        image = image.convert("RGBA")
    sidecar = art.load_sidecar(path)
    size = asset.size if isinstance(asset.size, list) and len(asset.size) == 2 else None
    frame_paths = manifest.frame_paths(asset)

    if frame_paths:
        missing = [p.name for _, _, p in frame_paths if not p.exists()]
        if missing:
            problems.append(f"{asset.id}: missing frame files {', '.join(missing)}")
        frames = [p for _, _, p in frame_paths if p.exists()]
        sizes = {}
        for frame in frames:
            with Image.open(frame) as img:
                sizes[frame.name] = list(img.size)
        wrong = [f"{n} is {w}x{h}" for n, (w, h) in sizes.items() if size and [w, h] != size]
        if wrong:
            problems.append(f"{asset.id}: frames must be {size[0]}x{size[1]}: " + ", ".join(wrong))
        loaded = load_frames(manifest, asset)
        if loaded and not wrong:
            image, _ = art.build_sheet(loaded)  # check the palette across every frame
    elif sidecar is not None:
        frame_size = sidecar.get("frame_size")
        if size and frame_size != size:
            problems.append(f"{asset.id}: frames are {frame_size[0]}x{frame_size[1]}, manifest says {size[0]}x{size[1]}")
        counts = {name: len(frames) for name, frames in sidecar.get("animations", {}).items()}
        if asset.frames and counts != asset.frames:
            problems.append(f"{asset.id}: animations {counts} don't match manifest frames {asset.frames}")
    elif size:
        if asset.kind == "tileset":
            if image.width % size[0] or image.height % size[1]:
                problems.append(f"{asset.id}: {image.width}x{image.height} isn't a grid of {size[0]}x{size[1]} tiles")
        elif list(image.size) != size:
            problems.append(f"{asset.id}: image is {image.width}x{image.height}, manifest says {size[0]}x{size[1]}")
        if asset.frames and sum(asset.frames.values()) > 1:
            problems.append(f"{asset.id}: manifest lists animation frames but there's no {path.with_suffix('.json').name}")

    if colors:
        off, partial = art.off_palette(image, colors)
        if off:
            worst = sorted(off.items(), key=lambda kv: -kv[1])[:5]
            listed = ", ".join(f"{c} ({n}px)" for c, n in worst)
            more = f" and {len(off) - 5} more" if len(off) > 5 else ""
            problems.append(f"{asset.id}: {len(off)} off-palette colors: {listed}{more}")
        if partial:
            problems.append(f"{asset.id}: {partial} semi-transparent pixels (pixel art usually wants 0 or 255 alpha)")
    return problems


def preview_items(manifest: Manifest, assets: list[Asset]) -> list[tuple[str, Image.Image]]:
    items: list[tuple[str, Image.Image]] = []
    for a in assets:
        path = manifest.asset_path(a)
        frames = load_frames(manifest, a)
        if frames and len({i.size for f in frames.values() for i in f}) == 1:
            items.append((a.id, art.build_sheet(frames)[0]))
        elif path.suffix.lower() == ".png" and path.exists():
            with Image.open(path) as image:
                items.append((a.id, image.convert("RGBA")))
    return items


SFX_MAX_SECONDS = 5.0


def check_wav(manifest: Manifest, asset: Asset) -> list[str]:
    """Problems with a sound effect file: format, length, clipping, silence."""
    path = manifest.asset_path(asset)
    if not path.exists():
        return [f"{asset.id}: {manifest.output}/{asset.file} doesn't exist yet"]
    try:
        channels, bits, rate, seconds = audio.wav_format(path)
    except audio.AudioError as error:
        return [f"{asset.id}: {error}"]
    problems = []
    if channels != 1:
        problems.append(f"{asset.id}: {channels} channels; sound effects should be mono (run `sfx clean`)")
    if bits != 16:
        problems.append(f"{asset.id}: {bits}-bit; expected 16-bit")
    if rate not in (44100, 48000):
        problems.append(f"{asset.id}: {rate} Hz; expected 44100 or 48000")
    if asset.kind == "sfx" and seconds > SFX_MAX_SECONDS:
        problems.append(f"{asset.id}: {seconds:.1f} s long; sound effects are usually under {SFX_MAX_SECONDS:.0f} s")
    info = audio.describe(audio.read(path))
    if info.peak_db < -60:
        problems.append(f"{asset.id}: silent")
    elif info.clipped > 10:
        problems.append(f"{asset.id}: {info.clipped} clipped samples (distorted); run `sfx clean` to lower it")
    return problems


def sfx_source(manifest: Manifest, asset: Asset):
    src = manifest.source_path(asset)
    if src is None or src.suffix.lower() not in (".yaml", ".yml"):
        raise audio.AudioError(f"{asset.id}: no sfxr parameter file (set source: sfxr, or src: sounds/<id>.yaml)")
    return src


def make_sfx(manifest: Manifest, asset: Asset, peak_db: float | None = None) -> list[str]:
    """Renders an sfxr parameter file into the asset's WAV (cleaned); returns check problems."""
    src = sfx_source(manifest, asset)
    if not src.exists():
        raise audio.AudioError(f"{src} not found; create it with `gamekit sfx new {asset.id} --preset <name>`")
    try:
        params = sfxr.load(src)
    except ValueError as error:
        raise audio.AudioError(str(error)) from None
    out = manifest.asset_path(asset)
    if out.suffix.lower() != ".wav":
        raise audio.AudioError(f"{asset.id}: sfxr makes .wav files, but file is {asset.file}")
    peak = manifest.sfx_peak_db if peak_db is None else peak_db
    audio.write_wav(out, audio.clean(sfxr.render(params), peak_db=peak))
    return check_wav(manifest, asset)


def clean_into(manifest: Manifest, asset: Asset, source, do_trim: bool = True,
               peak_db: float | None = None) -> list[str]:
    """Any sound file -> the asset's cleaned WAV; returns check problems."""
    out = manifest.asset_path(asset)
    if out.suffix.lower() != ".wav":
        raise audio.AudioError(f"{asset.id}: clean writes .wav files, but file is {asset.file}")
    peak = manifest.sfx_peak_db if peak_db is None else peak_db
    audio.write_wav(out, audio.clean(audio.read(source), do_trim=do_trim, peak_db=peak))
    return check_wav(manifest, asset)


def check_ogg(manifest: Manifest, asset: Asset, loop_source: Path | None = None) -> list[str]:
    """Problems with a music file: not Ogg Vorbis, silent, clipping, or a loop that won't be seamless."""
    path = manifest.asset_path(asset)
    if not path.exists():
        return [f"{asset.id}: {manifest.output}/{asset.file} doesn't exist yet"]
    with open(path, "rb") as f:
        if f.read(4) != b"OggS":
            return [f"{asset.id}: {asset.file} is not an Ogg file"]
    info = music.describe(path, loop_source)  # needs ffmpeg to decode
    problems = []
    if info.lufs is None or info.lufs < -60:
        problems.append(f"{asset.id}: silent")
    if info.true_peak is not None and info.true_peak > 0.0:
        problems.append(f"{asset.id}: peaks at {info.true_peak:+.1f} dBTP (clips); re-encode with --loudness")
    if manifest.loops(asset):
        problems += music.seam_problems(asset.id, info)
    return problems


def music_assets(manifest: Manifest, ids: list[str]) -> list[Asset]:
    if ids:
        by_id = {a.id: a for a in manifest.assets}
        missing = [i for i in ids if i not in by_id]
        if missing:
            raise music.MusicError(f"not in the manifest: {', '.join(missing)}")
        return [by_id[i] for i in ids]
    return [a for a in manifest.assets if a.kind == "music" and a.source == "synth"]


def render_music(manifest: Manifest, assets: list[Asset], godot: str, loudness: float | None,
                 keep_wav: Path | None = None) -> list[tuple[Asset, list[str]]]:
    """Renders the game's scores with its Godot script, then encodes each to the asset's OGG."""
    script = manifest.music.get("render_script")
    if not script:
        raise music.MusicError("set music.render_script in assets.yaml (the game's Godot script that writes WAVs)")
    if loudness is None:
        loudness = manifest.music_lufs
    project = manifest.root / str(manifest.music.get("godot_project", "."))
    for a in assets:
        if not a.file.lower().endswith(".ogg"):
            raise music.MusicError(f"{a.id}: music files are .ogg, but file is {a.file}")
    with music.temp_dir() as tmp:
        out_dir = keep_wav or Path(tmp)
        out_dir.mkdir(parents=True, exist_ok=True)
        wavs = music.render_wavs(godot, project.resolve(), str(script),
                                 [manifest.track_name(a) for a in assets], out_dir.resolve())
        results = []
        for a in assets:
            wav = wavs[manifest.track_name(a)]
            music.encode_ogg(wav, manifest.asset_path(a), loudness)
            results.append((a, check_ogg(manifest, a, loop_source=wav)))
    return results
