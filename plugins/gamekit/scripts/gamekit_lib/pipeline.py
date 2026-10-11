"""Manifest-aware art steps: draw (text sprite -> PNG), export (Aseprite), check, preview."""
from __future__ import annotations

from PIL import Image

from . import art, aseprite
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
    art.save(image, sidecar, manifest.asset_path(asset))
    return check(manifest, asset, [e.color for e in entries])


def export(manifest: Manifest, asset: Asset, exe: str | None = None) -> list[str]:
    """Exports the asset's .aseprite file with the Aseprite CLI; returns check problems."""
    src = manifest.source_path(asset)
    if src is None or src.suffix.lower() not in (".aseprite", ".ase"):
        raise aseprite.AsepriteError(f"{asset.id}: no .aseprite source (set src: or source: self)")
    out = manifest.asset_path(asset)
    sidecar = aseprite.export(src, out, exe)
    with Image.open(out) as image:
        art.save(image.copy(), sidecar, out)
    return check(manifest, asset, [e.color for e in palette_entries(manifest)])


def check(manifest: Manifest, asset: Asset, colors: list[Color]) -> list[str]:
    """Problems with an asset's finished PNG: missing file, wrong size or frames, off-palette colors."""
    path = manifest.asset_path(asset)
    if path.suffix.lower() != ".png":
        return []
    if not path.exists():
        return [f"{asset.id}: {manifest.output}/{asset.file} doesn't exist yet"]
    problems: list[str] = []
    with Image.open(path) as image:
        image = image.convert("RGBA")
    sidecar = art.load_sidecar(path)
    size = asset.size if isinstance(asset.size, list) and len(asset.size) == 2 else None

    if sidecar is not None:
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
        if path.suffix.lower() == ".png" and path.exists():
            with Image.open(path) as image:
                items.append((a.id, image.convert("RGBA")))
    return items
