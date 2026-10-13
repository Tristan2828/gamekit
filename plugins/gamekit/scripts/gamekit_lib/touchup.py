"""Touch up with Claude: an AI sprite's pixels as an editable text sprite (art/<id>.yaml).

Pictures shrunk to 8-16 px are good drafts but lose faces, eyes and clean outlines. Claude fixes those best
pixel by pixel, in the text-row format of the art-draw skill. This writes the draft in that format (one
character per pixel, the palette's own one-letter names), switches the asset to `source: claude` and renders
it, so the game shows the draft at once and Claude edits real pixels instead of starting from nothing.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from . import art, manifest, pictures, pipeline
from .manifest import Asset, Manifest
from .palette import Color, Entry, to_hex

SPARE_KEYS = "0123456789@#$%&*+=?!<>~^"  # for colors that aren't in the palette (rare after snapping)


class TouchUpError(Exception):
    pass


def text_sprite(frames: dict[str, list[Image.Image]], entries: list[Entry], still: bool, title: str) -> str:
    """The frames ({animation: [images]}) as a text sprite: one character per pixel, "." for see-through."""
    by_color = {color: char for char, color in art.palette_keys(entries).items()}
    extra: dict[Color, str] = {}
    blocks: dict[str, list[str]] = {}
    for anim, images in frames.items():
        rendered = []
        for image in images:
            image = image.convert("RGBA")
            pixels = image.load()
            rows = []
            for y in range(image.height):
                row = ""
                for x in range(image.width):
                    r, g, b, a = pixels[x, y]
                    if a < 128:
                        row += "."
                        continue
                    if (r, g, b) not in by_color and (r, g, b) not in extra:
                        spare = [c for c in SPARE_KEYS if c not in by_color.values() and c not in extra.values()]
                        if not spare:
                            raise TouchUpError("too many colors that aren't in the palette: snap to the palette first")
                        extra[(r, g, b)] = spare[0]
                    row += by_color.get((r, g, b)) or extra[(r, g, b)]
                rows.append(row)
            rendered.append("\n".join(rows))
        blocks[anim] = rendered
    lines = [f"# {title}"]
    if extra:  # a keys block replaces the palette's names, so it lists every character used
        used = {c for texts in blocks.values() for text in texts for c in text if c not in ".\n"}
        lines.append("keys:")
        for char in sorted(used):
            color = next((col for col, ch in by_color.items() if ch == char), None) or \
                next(col for col, ch in extra.items() if ch == char)
            lines.append(f"  '{char}': '{to_hex(color).lstrip('#')}'")  # quoted: YAML reads 010203 as a number
    if still:
        lines.append("rows: |")
        lines += ["  " + row for row in next(iter(blocks.values()))[0].splitlines()]
    else:
        lines.append("frames:")
        for anim, texts in blocks.items():
            lines.append(f"  {anim}:")
            for text in texts:
                lines.append("    - |")
                lines += ["      " + row for row in text.splitlines()]
    return "\n".join(lines) + "\n"


def source_file(loaded: Manifest, asset: Asset) -> Path:
    """Where the text sprite goes: the asset's `src` if that's a .yaml, else art/<id>.yaml."""
    if asset.src and asset.src.lower().endswith((".yaml", ".yml")):
        return loaded.root / asset.src
    return loaded.root / manifest.DEFAULT_SOURCES["claude"].format(id=asset.id)


def by_animation(loaded: Manifest, asset: Asset, sprites: dict[str, Image.Image]) -> dict[str, list[Image.Image]]:
    """{frame file name: sprite} -> {animation: [frames in order]}. Frames without a sprite copy the nearest one
    before them in that animation (or the first frame), so Claude has something to edit."""
    paths = loaded.frame_paths(asset)
    if not paths:
        return {"": [next(iter(sprites.values()))]}
    first = sprites.get(paths[0][2].stem) or next(iter(sprites.values()))
    out: dict[str, list[Image.Image]] = {}
    for anim, _, path in paths:
        frames = out.setdefault(anim, [])
        frames.append(sprites.get(path.stem) or (frames[-1] if frames else first))
    return out


def current_frames(loaded: Manifest, asset: Asset) -> dict[str, list[Image.Image]]:
    """The asset's finished PNG(s) as {animation: [frames]}."""
    frames = pipeline.load_frames(loaded, asset)
    if frames:
        return frames
    path = loaded.asset_path(asset)
    if loaded.frame_paths(asset):
        missing = [p.name for _, _, p in loaded.frame_paths(asset) if not p.exists()]
        raise TouchUpError(f"{asset.id} has no {', '.join(missing)} yet: use pictures for every frame first, "
                           "or touch it up from the pictures (Animate panel)")
    if not path.exists():
        raise TouchUpError(f"{asset.id} has no file yet ({loaded.output}/{asset.file})")
    with Image.open(path) as image:
        sidecar = art.load_sidecar(path)
        return art.split_sheet(image.convert("RGBA"), sidecar) if sidecar else {"": [image.convert("RGBA")]}


def write(loaded: Manifest, asset: Asset, frames: dict[str, list[Image.Image]], made_from: str,
          force: bool = False) -> tuple[Path, list[str]]:
    """Writes the text sprite, makes the asset `source: claude` (todo -> draft) and renders it; returns the
    text sprite's path and check problems."""
    target = source_file(loaded, asset)
    if target.exists() and not force:
        raise TouchUpError(f"REPLACE:{target.relative_to(loaded.root).as_posix()}")
    still = list(frames) == [""]
    size = f"{asset.size[0]}x{asset.size[1]}" if isinstance(asset.size, list) else ""
    title = (f"{asset.id}, {size}: a draft from {made_from}, shrunk by gamekit. Touch it up by hand "
             "(face, eyes, outline, silhouette), then `gamekit draw`.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text_sprite(frames, pipeline.palette_entries(loaded), still, title), encoding="utf-8")
    manifest.set_fields(loaded.path, asset.id, {"source": "claude"} | ({"status": "draft"} if asset.status == "todo" else {}))
    reloaded = manifest.load(loaded.path)
    fresh = next(a for a in reloaded.assets if a.id == asset.id)
    return target, pipeline.draw(reloaded, fresh)


def from_pictures(loaded: Manifest, asset: Asset, chosen: dict[str, str], background: bool = True, snap: bool = True,
                  outline: bool = True, force: bool = False) -> tuple[Path, list[str]]:
    """Touch-up draft straight from pictures: {frame file name: picture} (one shared crop, like Use all frames)."""
    if not chosen:
        raise TouchUpError("choose a picture first")
    if asset.frames and sum(asset.frames.values()) > 1 and not loaded.frame_paths(asset):
        raise TouchUpError(f"{asset.id} is animated and kept as one sheet: use a picture for it first, "
                           "then touch up its PNG (gamekit touchup)")
    if loaded.frame_paths(asset):
        sprites = pictures.make_frames(loaded, asset, chosen, background, snap, outline)
    else:
        sprites = {asset.id: pictures.make_sprite(loaded, asset, next(iter(chosen.values())), background, snap, outline)}
    names = ", ".join(dict.fromkeys(chosen.values()))
    return write(loaded, asset, by_animation(loaded, asset, sprites), f"AI pictures ({names})", force)


def from_files(loaded: Manifest, asset: Asset, force: bool = False) -> tuple[Path, list[str]]:
    """Touch-up draft from the asset's finished PNG(s)."""
    return write(loaded, asset, current_frames(loaded, asset), f"its PNG ({loaded.output}/{asset.file})", force)
