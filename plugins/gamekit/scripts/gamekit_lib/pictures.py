"""AI pictures for a game: the `pictures/` folder next to assets.yaml, and turning a picture into a sprite.

Each picture is a PNG with a .json beside it holding what made it (description, seed, size...), so a
take can be remade or adjusted. Removed pictures move to pictures/_removed/ rather than being deleted.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from PIL import Image, ImageDraw

from . import packs, pipeline
from .manifest import Asset, Manifest
from .palette import Color

FOLDER = "pictures"
MARK = (255, 0, 254)  # a color pictures don't use, to find the flood-filled background


class PictureError(Exception):
    pass


def folder(manifest: Manifest) -> Path:
    return manifest.root / FOLDER


def slug(text: str, limit: int = 40) -> str:
    words = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (words[:limit].rstrip("-") or "picture")


def new_path(manifest: Manifest, prompt: str, seed: int) -> Path:
    folder(manifest).mkdir(exist_ok=True)
    base = folder(manifest) / f"{slug(prompt)}-{seed}"
    path, n = base.with_suffix(".png"), 2
    while path.exists():
        path, n = base.parent / f"{base.name}-{n}.png", n + 1
    return path


def path_of(manifest: Manifest, name: str) -> Path:
    """A picture by file name (no folders), which must exist."""
    if not name or "/" in name or "\\" in name or name.startswith(".") or not name.endswith(".png"):
        raise PictureError(f"not a picture name: {name!r}")
    path = folder(manifest) / name
    if not path.is_file():
        raise PictureError(f"no picture called {name}")
    return path


def read_meta(path: Path) -> dict:
    try:
        return json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_meta(path: Path, meta: dict) -> None:
    path.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def record(path: Path, request: dict, answer: dict) -> dict:
    """Writes the settings that made a picture beside it."""
    meta = {"prompt": request.get("prompt", ""), "seed": answer.get("seed"), "width": answer.get("width"),
            "height": answer.get("height"), "steps": request.get("steps"), "tile": bool(request.get("tile")),
            "refs": [Path(r).name for r in request.get("refs", [])], "model": "FLUX.2 klein 4B",
            "made": time.strftime("%Y-%m-%d %H:%M"), "kept": False}
    write_meta(path, meta)
    return meta


def list_all(manifest: Manifest) -> list[dict]:
    """Every picture, newest first: {name, meta, mtime}."""
    where = folder(manifest)
    items = []
    for path in where.glob("*.png") if where.is_dir() else []:
        items.append({"name": path.name, "meta": read_meta(path), "mtime": int(path.stat().st_mtime)})
    return sorted(items, key=lambda item: -item["mtime"])


def keep(manifest: Manifest, name: str, kept: bool = True) -> None:
    path = path_of(manifest, name)
    meta = read_meta(path)
    meta["kept"] = kept
    write_meta(path, meta)


def remove(manifest: Manifest, name: str) -> Path:
    """Moves a picture (and its .json) into pictures/_removed/."""
    path = path_of(manifest, name)
    bin_ = folder(manifest) / "_removed"
    bin_.mkdir(exist_ok=True)
    for part in (path, path.with_suffix(".json")):
        if part.exists():
            target = bin_ / part.name
            if target.exists():
                target.unlink()
            shutil.move(str(part), target)
    return bin_ / path.name


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


def to_sprite(image: Image.Image, size: tuple[int, int], colors: list[Color] | None = None,
              background: bool = True) -> Image.Image:
    """A big picture as a small pixel art sprite: background removed, cropped to the subject, shrunk to fit
    `size` (centered, bottom-aligned so it stands on the ground), hard-edged, and snapped to `colors`."""
    image = remove_background(image) if background else image.convert("RGBA")
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
