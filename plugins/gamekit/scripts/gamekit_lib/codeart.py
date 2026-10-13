"""Art a game draws from text in its own code, shown on the asset page until a file replaces it.

`code_art: src/art/pixel_art.gd` in assets.yaml points at a Godot script holding the game's sprites
as text, one character per pixel:

    const PALETTE ... = { ".": Color(0, 0, 0, 0), "k": Color(0.09, 0.07, 0.11), ... }
    const SPRITES ... = { "bat": ["..kk..", ...], "bat_1": [...], "cultist_walk_1": [...], ... }

An asset's sprite is its `replaces` name, else its id; animation frames follow gamekit's frame file
names (bat, bat_1, cultist_walk_1, cultist_attack). The player-color characters "P" and "p" are drawn
as magenta #FF00FF and #800080, the same convention as finished art files.
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

from .manifest import Asset, Manifest, frame_names

TINT = {"P": (255, 0, 255), "p": (128, 0, 128)}
_cache: dict[Path, tuple[float, dict[str, tuple[int, int, int, int]], dict[str, list[str]]]] = {}


class CodeArtError(Exception):
    pass


def _section(text: str, name: str) -> str:
    """The `{ ... }` body of `const <name>`, braces matched."""
    found = re.search(r"^const\s+" + name + r"\b[^=]*=\s*\{", text, re.M)
    if not found:
        raise CodeArtError(f"no `const {name} = {{...}}` found")
    depth, start = 1, found.end()
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i]
    raise CodeArtError(f"`const {name}` never closes")


def _color(args: str, where: str) -> tuple[int, int, int, int]:
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", args)]
    if len(numbers) not in (3, 4):
        raise CodeArtError(f"{where}: can't read Color({args})")
    if len(numbers) == 3:
        numbers.append(1.0)
    return tuple(max(0, min(255, round(n * 255))) for n in numbers)  # type: ignore[return-value]


def parse(text: str) -> tuple[dict[str, tuple[int, int, int, int]], dict[str, list[str]]]:
    """(palette char -> RGBA, sprite name -> rows) from a script's PALETTE and SPRITES."""
    palette = {char: _color(args, f"PALETTE {char!r}") for char, args in
               re.findall(r'"(.)"\s*:\s*Color\(([^)]*)\)', _section(text, "PALETTE"))}
    body = re.sub(r"#[^\n\"]*$", "", _section(text, "SPRITES"), flags=re.M)  # comments outside strings
    sprites = {name: re.findall(r'"([^"]*)"', rows) for name, rows in
               re.findall(r'"([A-Za-z0-9_]+)"\s*:\s*\[(.*?)\]', body, re.S)}
    return palette, {name: rows for name, rows in sprites.items() if rows}


def load(manifest: Manifest) -> tuple[dict[str, tuple[int, int, int, int]], dict[str, list[str]]] | None:
    """The game's code art, or None if `code_art` isn't set. Read again only when the file changes."""
    if not manifest.code_art:
        return None
    path = (manifest.root / manifest.code_art).resolve()
    if not path.is_file():
        raise CodeArtError(f"code_art: {manifest.code_art} not found")
    mtime = path.stat().st_mtime
    if path not in _cache or _cache[path][0] != mtime:
        _cache[path] = (mtime, *parse(path.read_text(encoding="utf-8")))
    return _cache[path][1], _cache[path][2]


def sprite_name(asset: Asset) -> str:
    return asset.replaces or asset.id


def has_art(manifest: Manifest, asset: Asset) -> bool:
    try:
        found = load(manifest)
    except CodeArtError:
        return False
    return bool(found) and sprite_name(asset) in found[1]


def render_rows(rows: list[str], palette: dict[str, tuple[int, int, int, int]], where: str) -> Image.Image:
    width = max(len(r) for r in rows)
    image = Image.new("RGBA", (width, len(rows)), (0, 0, 0, 0))
    pixels = image.load()
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            if char in TINT:
                pixels[x, y] = (*TINT[char], 255)
            elif char in palette:
                pixels[x, y] = palette[char]
            elif char != ".":  # "." is transparent even if the palette doesn't list it

                raise CodeArtError(f"{where}: unknown character {char!r} at row {y + 1}, column {x + 1}")
    return image


def render(manifest: Manifest, asset: Asset) -> Image.Image | None:
    """The asset drawn from the game's code: one row per animation, frames left to right (like a sheet).
    Frames the code doesn't have are left out; None if it has none of them."""
    found = load(manifest)
    if not found:
        return None
    palette, sprites = found
    animations: dict[str, list[Image.Image]] = {}
    for anim, _, name in frame_names(asset, sprite_name(asset)):
        if name in sprites:
            animations.setdefault(anim, []).append(render_rows(sprites[name], palette, name))
    if not animations:
        return None
    cell_w = max(f.width for frames in animations.values() for f in frames)
    cell_h = max(f.height for frames in animations.values() for f in frames)
    columns = max(len(frames) for frames in animations.values())
    sheet = Image.new("RGBA", (cell_w * columns, cell_h * len(animations)), (0, 0, 0, 0))
    for row, frames in enumerate(animations.values()):
        for col, frame in enumerate(frames):  # bottom-centered, so feet line up
            sheet.paste(frame, (col * cell_w + (cell_w - frame.width) // 2, row * cell_h + cell_h - frame.height))
    return sheet
