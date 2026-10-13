"""AI pictures for a game: the `pictures/` folder next to assets.yaml, and turning a picture into a sprite.

Each picture is a PNG with a .json beside it holding what made it (description, seed, size...), so a
take can be remade or adjusted. Removed pictures move to pictures/_removed/ (see made.py).

A cut-out is a copy of a picture with its background made transparent by the cut-out engine (BiRefNet).
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw

from . import made, palette, pipeline
from .made import MadeError as PictureError
from .manifest import Asset, Manifest
from .palette import Color

MARK = (255, 0, 254)  # a color pictures don't use, to find the flood-filled background


def folder(manifest: Manifest) -> Path:
    return made.folder(manifest, "picture")


def new_path(manifest: Manifest, prompt: str, seed: int) -> Path:
    return made.new_path(manifest, "picture", prompt, seed)


def path_of(manifest: Manifest, name: str) -> Path:
    return made.path_of(manifest, "picture", name)


read_meta = made.read_meta
slug = made.slug


def record(path: Path, request: dict, answer: dict) -> dict:
    """Writes the settings that made a picture beside it."""
    return made.record(path, {"prompt": request.get("prompt", ""), "seed": answer.get("seed"),
                              "width": answer.get("width"), "height": answer.get("height"),
                              "steps": request.get("steps"), "tile": bool(request.get("tile")),
                              "refs": [Path(r).name for r in request.get("refs", [])], "model": "FLUX.2 klein 4B",
                              "for": request.get("for", "")})


def cutout_path(manifest: Manifest, name: str) -> Path:
    """A free file name for a cut-out of picture `name`: <name>-cutout.png (numbered if taken)."""
    source = path_of(manifest, name)
    path, n = source.with_name(f"{source.stem}-cutout.png"), 2
    while path.exists():
        path, n = source.with_name(f"{source.stem}-cutout-{n}.png"), n + 1
    return path


def record_cutout(path: Path, name: str, source_meta: dict) -> dict:
    """A cut-out keeps what made its picture, plus which picture it was cut from."""
    keep = {k: v for k, v in source_meta.items() if k not in ("made", "kept", "cutout_of")}
    return made.record(path, keep | {"cutout_of": name, "cutout_model": "BiRefNet lite"})


def list_all(manifest: Manifest) -> list[dict]:
    return made.list_all(manifest, "picture")


def keep(manifest: Manifest, name: str, kept: bool = True) -> None:
    made.keep(manifest, "picture", name, kept)


def remove(manifest: Manifest, name: str) -> Path:
    return made.remove(manifest, "picture", name)


# --- picture -> sprite ----------------------------------------------------------------------------

def remove_background(image: Image.Image, tolerance: int = 48) -> Image.Image:
    """Makes the background transparent: flood-fills from every corner over colors close to the corner's
    (pictures asked for "on a plain background" have one), so the subject's own similar colors survive."""
    rgb = image.convert("RGB")
    marked = rgb.copy()
    w, h = marked.size
    for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if marked.getpixel(corner) != MARK:
            ImageDraw.floodfill(marked, corner, MARK, thresh=tolerance)
    out = image.convert("RGBA")
    alpha = Image.new("L", (w, h), 255)
    alpha_pixels, marked_pixels = alpha.load(), marked.load()
    for y in range(h):
        for x in range(w):
            if marked_pixels[x, y] == MARK:
                alpha_pixels[x, y] = 0
    out.putalpha(alpha)
    return out


def has_transparency(image: Image.Image) -> bool:
    return image.mode in ("RGBA", "LA") and image.getchannel("A").getextrema()[0] < 255


def to_sprite(image: Image.Image, size: tuple[int, int], colors: list[Color] | None = None,
              background: bool = True, outline: Color | None = None) -> Image.Image:
    """A big picture as a small pixel art sprite: background removed, cropped to the subject, shrunk to fit
    `size` (centered, bottom-aligned so it stands on the ground), hard-edged, and snapped to `colors`.
    A picture that already has a transparent background (a cut-out) keeps it. With `outline`, the subject is
    shrunk 2 px smaller and gets a 1 px outline of that color, still inside `size`."""
    if outline:
        inner = to_sprite(image, (max(1, size[0] - 2), max(1, size[1] - 2)), colors, background)
        sprite = Image.new("RGBA", size, (0, 0, 0, 0))
        sprite.paste(inner, (1, 1))
        return add_outline(sprite, outline)
    image = remove_background(image) if background and not has_transparency(image) else image.convert("RGBA")
    box = image.getchannel("A").getbbox()
    if box is None:
        raise PictureError("the whole picture is background: try without removing the background")
    subject = image.crop(box)
    scale = min(size[0] / subject.width, size[1] / subject.height)
    small = (max(1, round(subject.width * scale)), max(1, round(subject.height * scale)))
    shrunk = _shrink(subject, small, colors)
    sprite = Image.new("RGBA", size, (0, 0, 0, 0))
    sprite.paste(shrunk, ((size[0] - small[0]) // 2, size[1] - small[1]))
    return sprite


CELL = 6  # with a palette, each sprite pixel is decided by a 6x6 patch of the picture


def _shrink(subject: Image.Image, small: tuple[int, int], colors: list[Color] | None) -> Image.Image:
    """Shrinks to `small` with hard edges. With `colors`, the picture is first shrunk to CELL times the size
    and snapped to the palette, then each sprite pixel takes its patch's most common color: details such as
    eyes keep their own color instead of being averaged into mud. Without, each pixel is the average."""
    cell = CELL if colors else 1
    big = (small[0] * cell, small[1] * cell)
    # premultiply, so transparent pixels' colors don't bleed into the edges while shrinking
    premultiplied = Image.new("RGBA", subject.size, (0, 0, 0, 0))
    premultiplied.paste(subject, mask=subject.getchannel("A"))
    shrunk = premultiplied.resize(big, Image.Resampling.BOX)
    alpha = subject.getchannel("A").resize(big, Image.Resampling.BOX)
    pixels, alphas = shrunk.load(), alpha.load()
    for y in range(big[1]):
        for x in range(big[0]):
            r, g, b, a = pixels[x, y]
            if alphas[x, y] < 128:
                pixels[x, y] = (0, 0, 0, 0)
            else:  # undo the premultiply: average over the covered part only
                k = 255 / max(a, 1)
                pixels[x, y] = (min(255, round(r * k)), min(255, round(g * k)), min(255, round(b * k)), 255)
    if colors:
        shrunk = snap_to_palette(shrunk, colors)
        pixels = shrunk.load()
    if cell == 1:
        return shrunk
    out = Image.new("RGBA", small, (0, 0, 0, 0))
    for y in range(small[1]):
        for x in range(small[0]):
            solid = [pixels[x * cell + i, y * cell + j][:3] for j in range(cell) for i in range(cell)
                     if pixels[x * cell + i, y * cell + j][3]]
            if len(solid) * 2 >= cell * cell:  # at least half covered
                out.putpixel((x, y), (*Counter(solid).most_common(1)[0][0], 255))
    return out


def _lab(color: Color) -> tuple[float, float, float]:
    """A color in CIELAB: lightness, green-red, blue-yellow (distances there match how different colors look)."""
    def linear(v: float) -> float:
        v /= 255
        return ((v + 0.055) / 1.055) ** 2.4 if v > 0.04045 else v / 12.92

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    r, g, b = (linear(v) for v in color)
    x = f((0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047)
    y = f(0.2126 * r + 0.7152 * g + 0.0722 * b)
    z = f((0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883)
    return 116 * y - 16, 500 * (x - y), 200 * (y - z)


def snap_to_palette(image: Image.Image, colors: list[Color]) -> Image.Image:
    """Every visible pixel to the palette color nearest in hue, with lightness counting half: AI pictures are
    often paler than a game's palette, and a plain distance then picks a grey over the right green or purple."""
    image = image.convert("RGBA")
    palette_labs = [(c, _lab(c)) for c in colors]
    pixels = image.load()
    cache: dict[Color, Color] = {}
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            if not a:
                continue
            if (r, g, b) not in cache:
                lt, ga, bb = _lab((r, g, b))
                cache[(r, g, b)] = min(palette_labs, key=lambda e: (0.5 * (lt - e[1][0])) ** 2 + (ga - e[1][1]) ** 2
                                       + (bb - e[1][2]) ** 2)[0]
            pixels[x, y] = (*cache[(r, g, b)], a)
    return image


def add_outline(sprite: Image.Image, color: Color) -> Image.Image:
    """Draws `color` on every see-through pixel that touches the subject's side (not just its corner)."""
    out = sprite.copy()
    src, dst = sprite.load(), out.load()
    w, h = sprite.size
    for y in range(h):
        for x in range(w):
            if src[x, y][3]:
                continue
            if any(0 <= x + dx < w and 0 <= y + dy < h and src[x + dx, y + dy][3]
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                dst[x, y] = (*color, 255)
    return out


def sprite_colors(manifest: Manifest) -> list[Color]:
    """The palette a picture snaps to: the game's palette without its reserved colors (e.g. player colors)."""
    reserved = {palette.parse_hex(c) for c in manifest.sprites.get("reserved_colors", []) or []}
    return [e.color for e in pipeline.palette_entries(manifest) if e.color not in reserved]


def frame_targets(manifest: Manifest, asset: Asset) -> list[str]:
    """What a picture can become for an asset: each frame file's name (frame_files), else the asset itself."""
    paths = manifest.frame_paths(asset)
    return [path.stem for _, _, path in paths] if paths else [asset.id]


def make_sprite(manifest: Manifest, asset: Asset, name: str, background: bool = True, snap: bool = True,
                outline: bool = True) -> Image.Image:
    """A picture as one image (or one frame) of an asset, following the game's sprite rules; not saved."""
    if not (isinstance(asset.size, list) and len(asset.size) == 2):
        raise PictureError(f"{asset.id} has no pixel size in the manifest")
    with Image.open(path_of(manifest, name)) as picture:
        colors = sprite_colors(manifest) if snap else None
        if asset.kind == "tileset":  # a texture fills the whole tile: no background to remove, no outline
            sprite = picture.convert("RGBA").resize((asset.size[0], asset.size[1]), Image.Resampling.BOX)
            return snap_to_palette(sprite, colors) if colors else sprite
        line = manifest.sprites.get("outline") if outline else None
        return to_sprite(picture, (asset.size[0], asset.size[1]), colors, background,
                         palette.parse_hex(line) if line else None)


def use_as_asset(manifest: Manifest, asset: Asset, name: str, background: bool = True,
                 snap: bool = True, outline: bool = True, frame: str = "") -> list[str]:
    """Makes a picture an image asset's file, or one of its frame files (`frame`, e.g. "ghoul_walk_1");
    returns check problems."""
    if asset.frames and sum(asset.frames.values()) > 1 and not manifest.frame_paths(asset):
        raise PictureError(f"{asset.id} is animated ({', '.join(f'{k} {v}' for k, v in asset.frames.items())}) and "
                           "kept as one sheet; a picture makes one frame. Ask Claude to draw the animation from it.")
    targets = frame_targets(manifest, asset)
    frame = frame or targets[0]
    if frame not in targets:
        raise PictureError(f"{asset.id} has no frame {frame!r}; there are: {', '.join(targets)}")
    sprite = make_sprite(manifest, asset, name, background, snap, outline)
    paths = {path.stem: path for _, _, path in manifest.frame_paths(asset)}
    if paths:
        paths[frame].parent.mkdir(parents=True, exist_ok=True)
        sprite.save(paths[frame])
    else:
        pipeline.save_image(manifest, asset, sprite, None)
    return pipeline.check(manifest, asset, [e.color for e in pipeline.palette_entries(manifest)])
