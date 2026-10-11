"""Text-row sprites -> PNG, palette checks, and preview sheets.

A text sprite is a YAML file (by default art/<id>.yaml) where each character is one
pixel. "." is transparent; every other character is a key for a palette color:

    keys:            # optional: char -> palette color name, index, or RRGGBB hex
      a: 0d0b12
    rows: |          # a still image...
      ..aa..
      .abba.
    frames:          # ...or animations: name -> list of frames
      idle:
        - |
          ..aa..
      walk:
        - |
          ...

Without a `keys` block, the palette's single-character color names are the keys.

Animated sprites become a sheet: one row per animation, frames left to right, plus a
JSON sidecar (<file>.json) giving each frame's position.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from PIL import Image, ImageDraw

from .palette import Color, Entry, keys as palette_keys, parse_hex, to_hex

TRANSPARENT = "."


class ArtError(Exception):
    pass


@dataclass
class TextSprite:
    keys: dict[str, Color]
    # animation name -> frames (each a list of rows); a still image is {"": [rows]}
    frames: dict[str, list[list[str]]] = field(default_factory=dict)

    @property
    def is_still(self) -> bool:
        return list(self.frames) == [""]


def load_text_sprite(path: str | Path, entries: list[Entry]) -> TextSprite:
    path = Path(path)
    if not path.exists():
        raise ArtError(f"{path} not found")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ArtError(f"{path}: expected a mapping with 'rows' or 'frames'")
    keys = _resolve_keys(data.get("keys"), entries, path)
    if "rows" in data and "frames" in data:
        raise ArtError(f"{path}: use 'rows' (still image) or 'frames' (animations), not both")
    if "rows" in data:
        frames = {"": [_rows(data["rows"], path, "rows")]}
    elif isinstance(data.get("frames"), dict) and data["frames"]:
        frames = {}
        for name, frame_list in data["frames"].items():
            if not isinstance(frame_list, list) or not frame_list:
                raise ArtError(f"{path}: frames.{name} must be a list of frames")
            frames[str(name)] = [_rows(f, path, f"frames.{name}[{i}]") for i, f in enumerate(frame_list)]
    else:
        raise ArtError(f"{path}: needs 'rows' (still image) or 'frames' (animations)")
    return TextSprite(keys, frames)


def _resolve_keys(raw: object, entries: list[Entry], path: Path) -> dict[str, Color]:
    if raw is None:
        return palette_keys(entries)
    if not isinstance(raw, dict):
        raise ArtError(f"{path}: 'keys' must map a character to a color")
    by_name = {e.name: e.color for e in entries if e.name}
    keys: dict[str, Color] = {}
    for char, value in raw.items():
        char = str(char)
        if len(char) != 1 or char == TRANSPARENT:
            raise ArtError(f"{path}: key {char!r} must be one character other than '.'")
        if isinstance(value, int) and not isinstance(value, bool):
            if not 0 <= value < len(entries):
                raise ArtError(f"{path}: key {char!r}: palette index {value} out of range (0-{len(entries) - 1})")
            keys[char] = entries[value].color
        elif str(value) in by_name:
            keys[char] = by_name[str(value)]
        elif len(str(value).lstrip("#")) == 6:
            try:
                keys[char] = parse_hex(str(value))
            except ValueError:
                raise ArtError(f"{path}: key {char!r}: {value!r} is not a color") from None
        else:
            raise ArtError(f"{path}: key {char!r}: {value!r} is not a palette name, index or RRGGBB")
    return keys


def _rows(block: object, path: Path, where: str) -> list[str]:
    if not isinstance(block, str):
        raise ArtError(f"{path}: {where} must be a text block (use `|`)")
    rows = [r.rstrip() for r in block.strip("\n").splitlines()]
    rows = [r for r in rows if r]
    if not rows:
        raise ArtError(f"{path}: {where} is empty")
    widths = {len(r) for r in rows}
    if len(widths) != 1:
        raise ArtError(f"{path}: {where}: rows have different lengths {sorted(widths)}")
    return rows


def render_frame(rows: list[str], keys: dict[str, Color], where: str = "") -> Image.Image:
    image = Image.new("RGBA", (len(rows[0]), len(rows)), (0, 0, 0, 0))
    pixels = image.load()
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            if char == TRANSPARENT:
                continue
            if char not in keys:
                raise ArtError(f"{where}: unknown key {char!r} at row {y + 1}, column {x + 1}")
            pixels[x, y] = (*keys[char], 255)
    return image


def render(sprite: TextSprite, where: str = "") -> tuple[Image.Image, dict | None]:
    """Returns the image (a sheet for animations) and the sidecar data (None for a still)."""
    rendered: dict[str, list[Image.Image]] = {
        name: [render_frame(rows, sprite.keys, f"{where} {name}[{i}]".strip()) for i, rows in enumerate(frames)]
        for name, frames in sprite.frames.items()}
    sizes = {img.size for imgs in rendered.values() for img in imgs}
    if len(sizes) != 1:
        raise ArtError(f"{where}: all frames must be the same size, got {sorted(sizes)}")
    if sprite.is_still:
        return rendered[""][0], None
    return build_sheet(rendered)


def build_sheet(animations: dict[str, list[Image.Image]]) -> tuple[Image.Image, dict]:
    w, h = next(iter(animations.values()))[0].size
    columns = max(len(frames) for frames in animations.values())
    sheet = Image.new("RGBA", (w * columns, h * len(animations)), (0, 0, 0, 0))
    sidecar: dict = {"frame_size": [w, h], "animations": {}}
    for row, (name, frames) in enumerate(animations.items()):
        sidecar["animations"][name] = []
        for col, frame in enumerate(frames):
            sheet.paste(frame, (col * w, row * h))
            sidecar["animations"][name].append([col * w, row * h])
    return sheet, sidecar


def save(image: Image.Image, sidecar: dict | None, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    side = sidecar_path(out)
    if sidecar is not None:
        side.write_text(json.dumps({"image": out.name, **sidecar}, indent=2) + "\n", encoding="utf-8")
    elif side.exists():
        side.unlink()


def sidecar_path(image_path: Path) -> Path:
    return image_path.with_suffix(".json")


def load_sidecar(image_path: Path) -> dict | None:
    side = sidecar_path(image_path)
    if not side.exists():
        return None
    return json.loads(side.read_text(encoding="utf-8"))


def off_palette(image: Image.Image, colors: list[Color]) -> tuple[dict[str, int], int]:
    """Colors not in the palette (hex -> pixel count) and the number of semi-transparent pixels.

    Fully transparent pixels are ignored."""
    allowed = set(colors)
    counts: dict[str, int] = {}
    partial = 0
    for count, (r, g, b, a) in image.convert("RGBA").getcolors(maxcolors=1 << 24) or []:
        if a == 0:
            continue
        if a != 255:
            partial += count
        if (r, g, b) not in allowed:
            key = to_hex((r, g, b))
            counts[key] = counts.get(key, 0) + count
    return counts, partial


def preview(items: list[tuple[str, Image.Image]], scale: int = 4, columns: int = 6) -> Image.Image:
    """A labelled contact sheet, scaled up with nearest-neighbor so pixels stay crisp."""
    if not items:
        raise ArtError("nothing to preview: no image assets have files yet")
    label_h = 12
    pad = 8
    cell_w = max(max(img.width for _, img in items) * scale, 64) + pad
    cell_h = max(img.height for _, img in items) * scale + label_h + pad
    cols = min(columns, len(items))
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * cell_w + pad, rows * cell_h + pad), (40, 36, 46, 255))
    draw = ImageDraw.Draw(sheet)
    for i, (name, img) in enumerate(items):
        x = pad + (i % cols) * cell_w
        y = pad + (i // cols) * cell_h
        big = img.resize((img.width * scale, img.height * scale), Image.Resampling.NEAREST)
        _checker(draw, x, y, big.width, big.height)
        sheet.alpha_composite(big, (x, y))
        draw.text((x, y + big.height + 1), name[: max(4, cell_w // 6)], fill=(230, 225, 215, 255))
    return sheet


def _checker(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, size: int = 8) -> None:
    for cy in range(0, h, size):
        for cx in range(0, w, size):
            shade = 70 if (cx // size + cy // size) % 2 else 58
            draw.rectangle([x + cx, y + cy, x + min(cx + size, w) - 1, y + min(cy + size, h) - 1],
                           fill=(shade, shade, shade + 6, 255))
