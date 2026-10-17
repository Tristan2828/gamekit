"""Ready-made asset packs: import them, record their license, and pull assets out of them.

A pack lives in packs/<name>/ next to the manifest:

    packs/<name>/pack.yaml   name, license {name, author, url}, source_url, license_file, notes,
                             download (the file in packs/ it came from), starred (files on the shortlist)
    packs/<name>/files/...   the pack's files, exactly as downloaded

Downloads waiting to be imported sit in packs/ itself (a .zip, .rar, .7z or a folder without a pack.yaml);
names starting with "_" or "." are left alone. Commit pack.yaml; the files can stay git-ignored.

Assets taken from a pack say `license: {pack: <name>}` in assets.yaml, so the license is
written down once, in pack.yaml. The license is never guessed: `add` only shows hints
from the pack's own license / readme files, and `use` refuses a pack with no license.
"""
from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from PIL import Image

from . import made, pictures
from .art import build_sheet
from .manifest import Asset, Manifest
from .palette import Color, parse_hex

IMAGE_TYPES = {".png", ".gif", ".bmp", ".jpg", ".jpeg", ".webp"}
AUDIO_TYPES = {".wav", ".ogg", ".mp3", ".flac"}
LICENSE_NAMES = re.compile(r"(licen[cs]e|copying|readme|credits?|attribution)", re.I)
# Phrases worth pointing out in a license file. Shown as hints, never applied automatically.
LICENSE_HINTS = [
    (re.compile(r"\bCC0\b|creative\s+commons\s+zero|public\s+domain", re.I), "CC0 / public domain"),
    (re.compile(r"\bCC[- ]BY[- ]SA\b|attribution[- ]share\s*alike", re.I), "CC-BY-SA"),
    (re.compile(r"\bCC[- ]BY[- ]NC\b|non[- ]?commercial", re.I), "non-commercial (CC-BY-NC or similar)"),
    (re.compile(r"\bCC[- ]BY\b(?![- ](SA|NC|ND))|creative\s+commons\s+attribution\b", re.I), "CC-BY"),
    (re.compile(r"\bGPL\b|general\s+public\s+license", re.I), "GPL"),
    (re.compile(r"\bMIT\s+licen[cs]e\b", re.I), "MIT"),
    (re.compile(r"\bOGA[- ]BY\b", re.I), "OGA-BY"),
    (re.compile(r"\bno\s+(re)?distribut|do\s+not\s+(re)?distribut|not\s+allowed\s+to\s+(re)?sell", re.I),
     "redistribution limits"),
    (re.compile(r"\bcredit\b|\battribut", re.I), "asks for credit"),
]
MAX_PACK_BYTES = 2 * 1024 ** 3      # refuse archives that unpack to more than 2 GB
MAX_PACK_FILES = 20000
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
ARCHIVES = {".zip", ".rar", ".7z"}
JUNK = ("__MACOSX", ".DS_Store", "Thumbs.db")


class PackError(Exception):
    pass


@dataclass
class Pack:
    name: str
    folder: Path
    license: dict[str, str] = field(default_factory=dict)
    source_url: str = ""
    license_file: str = ""
    notes: str = ""
    download: str = ""
    starred: list[str] = field(default_factory=list)

    @property
    def files_dir(self) -> Path:
        return self.folder / "files"

    def has_license(self) -> bool:
        return bool(self.license.get("name") and self.license.get("author"))


def packs_dir(root: Path) -> Path:
    return root / "packs"


def load(root: Path, name: str) -> Pack:
    folder = packs_dir(root) / name
    meta = folder / "pack.yaml"
    if not meta.exists():
        raise PackError(f"no pack named {name!r} (expected {meta}). Import it with `gamekit pack add`.")
    data = yaml.safe_load(meta.read_text(encoding="utf-8")) or {}
    return Pack(name=name, folder=folder,
                license={k: str(v) for k, v in (data.get("license") or {}).items() if v},
                source_url=str(data.get("source_url", "") or ""),
                license_file=str(data.get("license_file", "") or ""),
                notes=str(data.get("notes", "") or ""),
                download=str(data.get("download", "") or ""),
                starred=[str(s) for s in data.get("starred") or []])


def save(pack: Pack) -> None:
    data = {"name": pack.name,
            "license": {k: pack.license.get(k, "") for k in ("name", "author", "url")},
            "source_url": pack.source_url,
            "license_file": pack.license_file,
            "notes": pack.notes,
            "download": pack.download,
            "starred": sorted(set(pack.starred))}
    header = ("# Pack info for gamekit. Fill license from the pack's own license file or download page;\n"
              "# never guess. Assets from this pack use `license: {pack: " + pack.name + "}` in assets.yaml.\n")
    (pack.folder / "pack.yaml").write_text(header + yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def all_packs(root: Path) -> list[Pack]:
    folder = packs_dir(root)
    if not folder.exists():
        return []
    return [load(root, p.name) for p in sorted(folder.iterdir()) if (p / "pack.yaml").exists()]


def add(root: Path, source: Path, name: str) -> Pack:
    """Copies a downloaded .zip, .rar, .7z or folder into packs/<name>/files/ (never overwrites a pack)."""
    if not NAME_PATTERN.match(name):
        raise PackError(f"pack name {name!r} must be lowercase letters, digits, '-' or '_'")
    if not source.exists():
        raise PackError(f"{source} not found")
    folder = packs_dir(root) / name
    if folder.exists() or any(p.name.lower() == name for p in _entries(packs_dir(root))):  # Windows ignores case
        raise PackError(f"pack {name!r} already exists in {folder}; pick another name or delete it first")
    files = folder / "files"
    try:
        if source.is_dir():
            _copy_folder(source, files)
        elif zipfile.is_zipfile(source):
            _extract_zip(source, files)
        elif source.suffix.lower() in ARCHIVES:
            _extract_other(source, files)
        else:
            raise PackError(f"{source} is not a .zip, .rar, .7z or a folder")
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    _flatten_single_folder(files)
    pack = Pack(name=name, folder=folder)
    found = license_files(pack)
    pack.license_file = found[0] if found else ""
    if source.resolve().parent == packs_dir(root).resolve():
        pack.download = source.name  # so the downloads list knows it's imported
    save(pack)
    return pack


def _entries(folder: Path) -> list[Path]:
    return sorted(folder.iterdir()) if folder.is_dir() else []


def downloads(root: Path) -> list[dict]:
    """Downloads in packs/ not imported yet: archives and folders without a pack.yaml.
    {name, kind (zip/rar/7z/folder), size (bytes), suggested (a pack name)}."""
    folder = packs_dir(root)
    done = {p.download for p in all_packs(root) if p.download}
    taken = {p.name.lower() for p in _entries(folder)}
    out = []
    for path in _entries(folder):
        if path.name.startswith(("_", ".")) or path.name in done or path.is_symlink():
            continue
        if path.is_dir():
            if (path / "pack.yaml").exists():
                continue
            kind, size = "folder", sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
        elif path.suffix.lower() in ARCHIVES:
            kind, size = path.suffix.lower()[1:], path.stat().st_size
        else:
            continue
        out.append({"name": path.name, "kind": kind, "size": size, "suggested": suggest_name(path.name, taken)})
    return out


def suggest_name(filename: str, taken: set[str] = frozenset()) -> str:
    """A pack name from a download's file name: 'Foozle_Void Pack.zip' -> 'foozle-void-pack'."""
    stem = filename[:-len(Path(filename).suffix)] if Path(filename).suffix.lower() in ARCHIVES else filename
    base = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")[:48].rstrip("-") or "pack"
    name, n = base, 2
    while name in taken:
        name, n = f"{base}-{n}", n + 1
    return name


def _extract_other(archive: Path, dest: Path) -> None:
    """A .rar or .7z, with 7-Zip if installed, else Windows' own tar (it reads .rar and .7z too). Unpacked into a
    temporary folder first and then copied, which skips links and checks the size and file count limits."""
    tool = _unpacker()
    if tool is None:
        raise PackError(f"can't open {archive.name}: install 7-Zip (winget install 7zip.7zip), "
                        "or unpack it yourself into a folder in packs/")
    dest.parent.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="_unpack-", dir=dest.parent.parent) as temp:
        out = Path(temp) / "out"
        out.mkdir()
        if Path(tool).stem.lower().startswith("7z"):
            command = [tool, "x", "-y", f"-o{out}", str(archive)]
        else:
            command = [tool, "-xf", str(archive), "-C", str(out)]
        result = subprocess.run(command, capture_output=True, text=True, errors="replace")
        if result.returncode != 0:
            raise PackError(f"couldn't unpack {archive.name}: {(result.stderr or result.stdout).strip()[-300:]}")
        _copy_folder(out, dest)


def _unpacker() -> str | None:
    """7-Zip (PATH or its usual folder), else Windows' tar.exe (bsdtar, which reads .rar). Linux tar can't."""
    for name in ("7z", "7za"):
        found = shutil.which(name)
        if found:
            return found
    for base in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
        if base and (Path(base) / "7-Zip" / "7z.exe").exists():
            return str(Path(base) / "7-Zip" / "7z.exe")
    if sys.platform == "win32":
        tar = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tar.exe"
        if tar.exists():
            return str(tar)
    return None


def _extract_zip(archive: Path, dest: Path) -> None:
    """Extracts safely: no paths outside dest, no links, size and count limits."""
    dest.mkdir(parents=True)
    base = dest.resolve()
    with zipfile.ZipFile(archive) as z:
        members = [m for m in z.infolist() if not m.is_dir()]
        if len(members) > MAX_PACK_FILES:
            raise PackError(f"{archive} has {len(members)} files (limit {MAX_PACK_FILES})")
        if sum(m.file_size for m in members) > MAX_PACK_BYTES:
            raise PackError(f"{archive} unpacks to more than {MAX_PACK_BYTES // 1024 ** 3} GB")
        for m in members:
            if (m.external_attr >> 16) & 0o170000 == 0o120000:
                continue  # symlink
            name = m.filename.replace("\\", "/")
            if name.startswith("__MACOSX/") or Path(name).name in (".DS_Store", "Thumbs.db"):
                continue
            target = (base / name).resolve()
            if base != target and base not in target.parents:
                raise PackError(f"{archive}: refusing unsafe path {m.filename!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(m) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def _copy_folder(source: Path, dest: Path) -> None:
    count = total = 0
    for path in source.rglob("*"):
        rel = path.relative_to(source)
        if path.is_symlink() or not path.is_file() or any(part in JUNK for part in rel.parts):
            continue
        count += 1
        total += path.stat().st_size
        if count > MAX_PACK_FILES:
            raise PackError(f"{source} has more than {MAX_PACK_FILES} files")
        if total > MAX_PACK_BYTES:
            raise PackError(f"{source} is more than {MAX_PACK_BYTES // 1024 ** 3} GB")
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    if count == 0:
        raise PackError(f"{source} has no files")


def _flatten_single_folder(files: Path) -> None:
    """Many zips wrap everything in one top folder; lift its contents up a level."""
    entries = list(files.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        inner = entries[0]
        temp = files.parent / "_unwrap"
        inner.rename(temp)
        files.rmdir()
        temp.rename(files)


def list_files(pack: Pack) -> list[Path]:
    """Every file in the pack, relative to its files/ folder, sorted."""
    return sorted(p.relative_to(pack.files_dir) for p in pack.files_dir.rglob("*") if p.is_file())


def license_files(pack: Pack) -> list[str]:
    """Likely license / readme files, shallowest first."""
    found = [p for p in list_files(pack)
             if LICENSE_NAMES.search(p.name) and p.suffix.lower() in ("", ".txt", ".md", ".html", ".htm", ".rtf")]
    return [p.as_posix() for p in sorted(found, key=lambda p: (len(p.parts), p.as_posix()))]


def license_hints(pack: Pack) -> list[tuple[str, list[str]]]:
    """(file, hints) for each license-looking file: phrases to check, not a decision."""
    results = []
    for rel in license_files(pack)[:10]:
        text = (pack.files_dir / rel).read_text(encoding="utf-8", errors="replace")[:200_000]
        hints = [label for pattern, label in LICENSE_HINTS if pattern.search(text)]
        results.append((rel, hints))
    return results


def resolve(pack: Pack, rel: str) -> Path:
    """A file inside the pack; refuses paths that leave it."""
    base = pack.files_dir.resolve()
    path = (base / rel).resolve()
    if base not in path.parents or not path.is_file():
        raise PackError(f"{rel!r} is not a file in pack {pack.name!r} (see `gamekit pack list {pack.name}`)")
    return path


def describe(path: Path) -> str:
    if path.suffix.lower() in IMAGE_TYPES:
        try:
            with Image.open(path) as image:
                return f"{image.width}x{image.height}"
        except OSError:
            return "unreadable image"
    return f"{max(1, path.stat().st_size // 1024)} KB"


# --- taking images out of a pack -------------------------------------------------------

def parse_box(text: str) -> tuple[int, int, int, int]:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        raise PackError(f"--crop needs x,y,w,h in pixels, got {text!r}")
    x, y, w, h = (int(p) for p in parts)
    if w == 0 or h == 0:
        raise PackError("--crop width and height must be above 0")
    return x, y, w, h


def parse_anim(text: str) -> tuple[str, int, int, int]:
    """'walk=0,32,4' -> name, x, y, frame count (frames run left to right from x,y)."""
    match = re.fullmatch(r"([A-Za-z0-9_]+)=(\d+),(\d+),(\d+)", text.replace(" ", ""))
    if not match or int(match.group(4)) == 0:
        raise PackError(f"--anim needs name=x,y,count (e.g. walk=0,32,4), got {text!r}")
    return match.group(1), int(match.group(2)), int(match.group(3)), int(match.group(4))


def crop(image: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    x, y, w, h = box
    if x + w > image.width or y + h > image.height:
        raise PackError(f"crop {x},{y},{w},{h} goes outside the {image.width}x{image.height} image")
    return image.crop((x, y, x + w, y + h))


def slice_animations(image: Image.Image, frame: tuple[int, int],
                     anims: list[tuple[str, int, int, int]]) -> dict[str, list[Image.Image]]:
    """Cuts animation frames out of a pack's sheet (any layout) at the given frame size."""
    w, h = frame
    out: dict[str, list[Image.Image]] = {}
    for name, x, y, count in anims:
        if name in out:
            raise PackError(f"animation {name!r} given twice")
        out[name] = [crop(image, (x + i * w, y, w, h)) for i in range(count)]
    return out


def clean_alpha(image: Image.Image, threshold: int = 128) -> Image.Image:
    """Pixel art wants each pixel fully opaque or fully transparent."""
    image = image.convert("RGBA")
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            pixels[x, y] = (r, g, b, 255) if a >= threshold else (0, 0, 0, 0)
    return image


def resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Nearest-neighbor, so pixels stay crisp (whole-number scale factors look best)."""
    return image.resize(size, Image.Resampling.NEAREST)


def recolor(image: Image.Image, colors: list[Color]) -> tuple[Image.Image, int]:
    """Snaps every visible pixel to the nearest palette color; returns the image and pixels changed.

    Distance is "redmean" weighted RGB, a cheap approximation of how different colors look."""
    if not colors:
        raise PackError("can't recolor: the manifest has no palette")
    image = image.convert("RGBA")
    pixels = image.load()
    cache: dict[tuple[int, int, int], Color] = {}
    changed = 0
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            key = (r, g, b)
            if key not in cache:
                cache[key] = min(colors, key=lambda c: _distance(key, c))
            nr, ng, nb = cache[key]
            if (nr, ng, nb) != key:
                changed += 1
                pixels[x, y] = (nr, ng, nb, a)
    return image, changed


def _distance(a: Color, b: Color) -> float:
    rmean = (a[0] + b[0]) / 2
    dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return (2 + rmean / 256) * dr * dr + 4 * dg * dg + (2 + (255 - rmean) / 256) * db * db


def build(path: Path, crop_box: tuple[int, int, int, int] | None,
          anims: list[tuple[str, int, int, int]], frame: tuple[int, int] | None,
          target_size: tuple[int, int] | None) -> tuple[Image.Image, dict | None]:
    """Takes a still image (optionally cropped) or a sheet of animations out of a pack image,
    resized to `target_size` per frame when given. Returns the image and sidecar (None = still)."""
    with Image.open(path) as source:
        image = source.convert("RGBA")
    if anims:
        if frame is None:
            raise PackError("--anim needs the frame size: --frame WxH, or the asset's size in the manifest")
        if crop_box:
            image = crop(image, crop_box)
        animations = slice_animations(image, frame, anims)
        if target_size and target_size != frame:
            animations = {n: [resize(f, target_size) for f in fs] for n, fs in animations.items()}
        sheet, sidecar = build_sheet(animations)
        return clean_alpha(sheet), sidecar
    if crop_box:
        image = crop(image, crop_box)
    if target_size and target_size != image.size:
        image = resize(image, target_size)
    return clean_alpha(image), None


# --- the Packs tab: browsing, a shortlist, and taking a part of an image ---------------------------------

def images(pack: Pack) -> list[dict]:
    """Every image in a pack with its size: {file, width, height}. Unreadable images are left out."""
    out = []
    for rel in list_files(pack):
        if rel.suffix.lower() not in IMAGE_TYPES:
            continue
        try:
            with Image.open(pack.files_dir / rel) as image:
                out.append({"file": rel.as_posix(), "width": image.width, "height": image.height})
        except OSError:
            continue
    return out


def star(pack: Pack, rel: str, on: bool = True) -> None:
    """Adds a file to the pack's shortlist (starred: in pack.yaml), or takes it off."""
    resolve(pack, rel)
    pack.starred = [s for s in pack.starred if s != rel] + ([rel] if on else [])
    save(pack)


def cut(pack: Pack, rel: str, box: list[int] | tuple[int, ...] | None = None) -> Image.Image:
    """A part of a pack image (x, y, w, h; None = all of it), with pixels fully opaque or fully see-through."""
    path = resolve(pack, rel)
    if path.suffix.lower() not in IMAGE_TYPES:
        raise PackError(f"{rel} is not an image")
    with Image.open(path) as source:
        image = source.convert("RGBA")
    if box:
        if len(box) != 4 or any(not isinstance(v, int) or v < 0 for v in box) or not box[2] or not box[3]:
            raise PackError("the box needs x, y, width and height in whole pixels")
        image = crop(image, tuple(box))
    return clean_alpha(image)


def to_sprite(manifest: Manifest, asset: Asset, image: Image.Image, snap: bool = False,
              outline: bool = False) -> Image.Image:
    """A cut-out part of a pack image as one of the asset's images. The same size: used pixel for pixel (snapped
    to the palette if asked). Another size: shrunk or grown to fit, keeping its shape, the whole box counting (so
    frames boxed the same size get the same scale and don't jitter); a texture fills the whole tile."""
    if not (isinstance(asset.size, list) and len(asset.size) == 2):
        raise PackError(f"{asset.id} has no pixel size in the manifest")
    size = (asset.size[0], asset.size[1])
    colors = pictures.sprite_colors(manifest) if snap else None
    if image.size == size or asset.kind == "tileset":
        sprite = image if image.size == size else resize(image, size)
        return clean_alpha(pictures.snap_to_palette(sprite, colors)) if colors else sprite
    line = manifest.sprites.get("outline") if outline else None
    return pictures.to_sprite(image, size, colors, background=False, outline=parse_hex(line) if line else None,
                              box=(0, 0, image.width, image.height))


PICTURE_SIDE = 1024  # a part copied to the pictures is enlarged to about this size, as big as AI pictures are


def to_picture(manifest: Manifest, pack: Pack, rel: str, box: list[int] | None = None, for_id: str = "") -> Path:
    """Copies a part of a pack image into pictures/ as a picture: enlarged with whole pixels to about 1024 px, on a
    plain white background (the picture engine reads colors, not transparency), sides a multiple of 16. Then the
    Pictures tab can work from it (new AI pictures in its style), use it, or have Claude touch it up."""
    image = cut(pack, rel, box)
    longest = max(image.size)
    if longest <= PICTURE_SIDE:
        scale = max(1, PICTURE_SIDE // longest)
        big = resize(image, (image.width * scale, image.height * scale))
    else:
        scale = PICTURE_SIDE / longest
        big = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.BOX)
    side = lambda v: max(256, min(1536, math.ceil(v / 16) * 16))  # noqa: E731
    canvas = Image.new("RGB", (side(big.width), side(big.height)), (255, 255, 255))
    canvas.paste(big, ((canvas.width - big.width) // 2, (canvas.height - big.height) // 2), big)
    where = made.folder(manifest, "picture")
    where.mkdir(exist_ok=True)
    stem = made.slug(f"{pack.name} {Path(rel).stem}", 60) + (f"-{box[0]}-{box[1]}-{box[2]}x{box[3]}" if box else "")
    path, n = where / f"{stem}.png", 2
    while path.exists():
        path, n = where / f"{stem}-{n}.png", n + 1
    canvas.save(path)
    made.record(path, {"prompt": f"{pack.name}: {rel}", "width": canvas.width, "height": canvas.height,
                       "for": for_id, "pack": pack.name, "pack_file": rel, "box": list(box) if box else None,
                       "scale": scale if isinstance(scale, int) else round(scale, 3)})
    return path
