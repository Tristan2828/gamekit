"""Files the AI engines make for a game, before any of them becomes an asset.

Each kind has its own folder next to assets.yaml (pictures/, music-takes/). Every file has a .json beside it
holding what made it (description, seed, settings), so a take can be remade or adjusted. Removed files move
to <folder>/_removed/ rather than being deleted.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from .manifest import Manifest

KINDS = {"picture": ("pictures", ".png"), "music": ("music-takes", ".wav")}


class MadeError(Exception):
    pass


def folder(manifest: Manifest, kind: str) -> Path:
    return manifest.root / KINDS[kind][0]


def slug(text: str, limit: int = 40) -> str:
    words = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return words[:limit].rstrip("-") or "take"


def new_path(manifest: Manifest, kind: str, description: str, seed: int) -> Path:
    """A free file name for a new take: <description>-<seed>.<ext> (numbered if taken)."""
    where = folder(manifest, kind)
    where.mkdir(exist_ok=True)
    ext = KINDS[kind][1]
    base = where / f"{slug(description)}-{seed}"
    path, n = base.with_suffix(ext), 2
    while path.exists():
        path, n = where / f"{base.name}-{n}{ext}", n + 1
    return path


def path_of(manifest: Manifest, kind: str, name: str) -> Path:
    """A take by file name (no folders), which must exist."""
    ext = KINDS[kind][1]
    if not name or "/" in name or "\\" in name or name.startswith(".") or not name.endswith(ext):
        raise MadeError(f"not a {kind} name: {name!r}")
    path = folder(manifest, kind) / name
    if not path.is_file():
        raise MadeError(f"no {kind} called {name}")
    return path


def read_meta(path: Path) -> dict:
    try:
        return json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_meta(path: Path, meta: dict) -> None:
    path.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def record(path: Path, settings: dict) -> dict:
    """Writes the settings that made a take beside it (plus when, and not kept yet)."""
    meta = settings | {"made": time.strftime("%Y-%m-%d %H:%M"), "kept": False}
    write_meta(path, meta)
    return meta


def list_all(manifest: Manifest, kind: str) -> list[dict]:
    """Every take of a kind, newest first: {name, meta, mtime}."""
    where = folder(manifest, kind)
    items = [{"name": p.name, "meta": read_meta(p), "mtime": int(p.stat().st_mtime)}
             for p in (where.glob("*" + KINDS[kind][1]) if where.is_dir() else [])]
    return sorted(items, key=lambda item: -item["mtime"])


def keep(manifest: Manifest, kind: str, name: str, kept: bool = True) -> None:
    path = path_of(manifest, kind, name)
    meta = read_meta(path)
    meta["kept"] = kept
    write_meta(path, meta)


def remove(manifest: Manifest, kind: str, name: str) -> Path:
    """Moves a take (and its .json) into <folder>/_removed/."""
    path = path_of(manifest, kind, name)
    bin_ = folder(manifest, kind) / "_removed"
    bin_.mkdir(exist_ok=True)
    for part in (path, path.with_suffix(".json")):
        if part.exists():
            target = bin_ / part.name
            if target.exists():
                target.unlink()
            shutil.move(str(part), target)
    return bin_ / path.name
