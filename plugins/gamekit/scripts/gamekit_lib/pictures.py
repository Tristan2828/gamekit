"""AI pictures for a game: the `pictures/` folder next to assets.yaml, and turning a picture into a sprite.

Each picture is a PNG with a .json beside it holding what made it (description, seed, size...), so a
take can be remade or adjusted. Removed pictures move to pictures/_removed/ (see made.py).

A cut-out is a copy of a picture with its background made transparent by the cut-out engine (BiRefNet).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from . import made, packs, pipeline
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
                              "refs": [Path(r).name for r in request.get("refs", [])], "model": "FLUX.2 klein 4B"})


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
              background: bool = True) -> Image.Image:
    """A big picture as a small pixel art sprite: background removed, cropped to the subject, shrunk to fit
    `size` (centered, bottom-aligned so it stands on the ground), hard-edged, and snapped to `colors`.
    A picture that already has a transparent background (a cut-out) keeps it."""
    image = remove_background(image) if background and not has_transparency(image) else image.convert("RGBA")
    box = image.getchannel("A").getbbox()
    if box is None:
        raise PictureError("the whole picture is background: try without removing the background")
    subject = image.crop(box)
    scale = min(size[0] / subject.width, size[1] / subject.height)
    small = (max(1, round(subject.width * scale)), max(1, round(subject.height * scale)))
    # premultiply, so transparent pixels' colors don't bleed into the edges while shrinking
    premultiplied = Image.new("RGBA", subject.size, (0, 0, 0, 0))
    premultiplied.paste(subject, mask=subject.getchannel("A"))
    shrunk = premultiplied.resize(small, Image.Resampling.BOX)
    alpha = subject.getchannel("A").resize(small, Image.Resampling.BOX)
    pixels, alphas = shrunk.load(), alpha.load()
    for y in range(small[1]):
        for x in range(small[0]):
            r, g, b, a = pixels[x, y]
            coverage = alphas[x, y]
            if coverage < 128:
                pixels[x, y] = (0, 0, 0, 0)
            else:  # undo the premultiply: average over the covered part only
                k = 255 / max(a, 1)
                pixels[x, y] = (min(255, round(r * k)), min(255, round(g * k)), min(255, round(b * k)), 255)
    sprite = Image.new("RGBA", size, (0, 0, 0, 0))
    sprite.paste(shrunk, ((size[0] - small[0]) // 2, size[1] - small[1]))
    if colors:
        sprite, _ = packs.recolor(sprite, colors)
    return sprite


def use_as_asset(manifest: Manifest, asset: Asset, name: str, background: bool = True,
                 snap: bool = True) -> list[str]:
    """Makes a picture an image asset's file (one image, not an animation); returns check problems."""
    if not (isinstance(asset.size, list) and len(asset.size) == 2):
        raise PictureError(f"{asset.id} has no pixel size in the manifest")
    if asset.frames and sum(asset.frames.values()) > 1:
        raise PictureError(f"{asset.id} is animated ({', '.join(f'{k} {v}' for k, v in asset.frames.items())}); "
                           "a picture makes one frame. Ask Claude to draw the animation from it.")
    with Image.open(path_of(manifest, name)) as picture:
        colors = [e.color for e in pipeline.palette_entries(manifest)] if snap else None
        if asset.kind == "tileset":  # a texture fills the whole tile: no background to remove
            sprite = picture.convert("RGBA").resize((asset.size[0], asset.size[1]), Image.Resampling.BOX)
            if colors:
                sprite, _ = packs.recolor(sprite, colors)
        else:
            sprite = to_sprite(picture, (asset.size[0], asset.size[1]), colors, background)
    pipeline.save_image(manifest, asset, sprite, None)
    return pipeline.check(manifest, asset, [e.color for e in pipeline.palette_entries(manifest)])
