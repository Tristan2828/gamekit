"""Touch up with Claude: a picture's game-sized sprite as a new picture plus its pixels as editable text.

Pictures shrunk to 8-16 px are good drafts but lose faces, eyes and clean outlines. Claude fixes those best
pixel by pixel, in the text-row format of the art-draw skill. This keeps each draft in pictures/ as
<name>-touchup-<w>x<h>.png with a .yaml beside it (one character per pixel, the palette's own one-letter
names). Claude edits the .yaml and `render`s it back into the PNG. Nothing goes into the game until the
picture is used (Use on the Pictures tab, or picture-use), like any other picture.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from . import art, made, pictures, pipeline
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


def drafts(loaded: Manifest, asset: Asset, chosen: dict[str, str], background: bool = True, snap: bool = True,
           outline: bool = True, every_frame: bool = False) -> list[Path]:
    """Touch-up drafts in pictures/ from {frame file name: picture} (or {asset id: picture} for a still).
    Several frames share one crop, like Use all frames. With every_frame, frames without a picture start as
    a copy of the frame before them (or the first), so Claude has something to edit for each."""
    if not chosen:
        raise TouchUpError("choose a picture first")
    paths = loaded.frame_paths(asset)
    if not paths:
        name = next(iter(chosen.values()))
        sprites = {"": (pictures.make_sprite(loaded, asset, name, background, snap, outline), name, "")}
    else:
        made_frames = pictures.make_frames(loaded, asset, chosen, background, snap, outline)
        sprites, last = {}, ""
        first = next(p.stem for _, _, p in paths if p.stem in made_frames)
        for _, _, path in paths:
            frame = path.stem
            if frame in made_frames:
                sprites[frame], last = (made_frames[frame], chosen[frame], ""), frame
            elif every_frame:
                source = last or first
                sprites[frame] = (made_frames[source], chosen[source], source)
    entries = pipeline.palette_entries(loaded)
    saved = []
    for frame, (image, name, copy_of) in sprites.items():
        extra = {"touchup": True, "outline": outline, "snap": snap} | ({"copy_of": copy_of} if copy_of else {})
        png = pictures.keep_sprite(loaded, asset, image, name, frame, "touchup", extra)
        what = f"{asset.id}{' ' + frame if frame else ''}, {image.width}x{image.height}"
        title = (f"{what}: a draft from {name}" + (f" (a copy of {copy_of}, to change into this frame)" if copy_of else "")
                 + f". Touch it up by hand (face, eyes, outline, silhouette), then `gamekit touchup-render {png.name}`.")
        png.with_suffix(".yaml").write_text(text_sprite({"": [image]}, entries, True, title), encoding="utf-8")
        saved.append(png)
    return saved


def render(loaded: Manifest, name: str) -> tuple[Path, list[str]]:
    """Draws a touch-up picture again from its text rows (after Claude edited them); returns its PNG and
    problems."""
    png = pictures.path_of(loaded, Path(name).with_suffix(".png").name)
    text = png.with_suffix(".yaml")
    if not text.exists():
        raise TouchUpError(f"{png.name} has no text rows ({text.name}): press Touch up with Claude on it first")
    image, _ = art.render(art.load_text_sprite(text, pipeline.palette_entries(loaded)), text.name)
    meta = made.read_meta(png)
    problems = []
    if meta.get("width") and image.size != (meta["width"], meta["height"]):
        problems.append(f"it's {image.width}x{image.height}; {meta.get('for')} is {meta['width']}x{meta['height']}")
    image.save(png)
    return png, problems
