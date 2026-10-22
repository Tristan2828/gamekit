"""Export .aseprite files with the Aseprite command line (no MCP needed).

Each tag becomes an animation (one sheet row per tag); a file without tags becomes
a single animation named "default", or a still image when it has one frame.
The result uses the same sheet + JSON sidecar layout as art.py.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

WINDOWS_PATHS = [
    r"C:\Program Files\Aseprite\Aseprite.exe",
    r"C:\Program Files (x86)\Steam\steamapps\common\Aseprite\Aseprite.exe",
    r"C:\Program Files\Steam\steamapps\common\Aseprite\Aseprite.exe",
]
MAC_PATHS = [
    "/Applications/Aseprite.app/Contents/MacOS/aseprite",
    os.path.expanduser("~/Library/Application Support/Steam/steamapps/common/Aseprite/Aseprite.app/Contents/MacOS/aseprite"),
]
SEPARATOR = "#"


class AsepriteError(Exception):
    pass


def find() -> str:
    """The Aseprite executable: $GAMEKIT_ASEPRITE, then PATH, then the usual install folders."""
    configured = os.environ.get("GAMEKIT_ASEPRITE")
    if configured:
        if Path(configured).exists():
            return configured
        raise AsepriteError(f"GAMEKIT_ASEPRITE points to {configured}, which doesn't exist")
    for name in ("aseprite", "Aseprite"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in WINDOWS_PATHS + MAC_PATHS:
        if Path(candidate).exists():
            return candidate
    raise AsepriteError("Aseprite not found. Install it, add it to PATH, or set GAMEKIT_ASEPRITE "
                        "to the full path of Aseprite.exe.")


def export_command(exe: str, source: Path, png: Path, data: Path) -> list[str]:
    return [exe, "--batch", str(source),
            "--sheet", str(png), "--data", str(data),
            "--sheet-type", "rows", "--split-tags",
            "--filename-format", "{tag}" + SEPARATOR + "{tagframe}",
            "--format", "json-array"]


def export(source: Path, out_png: Path, exe: str | None = None) -> dict | None:
    """Exports `source` to `out_png`; returns the sidecar data (None for a one-frame still)."""
    if not source.exists():
        raise AsepriteError(f"{source} not found")
    exe = exe or find()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        data_path = Path(tmp) / "sheet.json"
        result = subprocess.run(export_command(exe, source, out_png, data_path),
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0 or not data_path.exists():
            raise AsepriteError(f"Aseprite failed on {source}: {(result.stderr or result.stdout).strip()}")
        raw = json.loads(data_path.read_text(encoding="utf-8"))
    return sidecar_from_aseprite(raw)


def sidecar_from_aseprite(raw: dict) -> dict | None:
    """Turns Aseprite's json-array data into gamekit's sidecar layout."""
    frames = raw.get("frames")
    if not isinstance(frames, list) or not frames:
        raise AsepriteError("Aseprite data has no frames")
    animations: dict[str, list[list[int]]] = {}
    size: list[int] | None = None
    for frame in frames:
        tag = str(frame.get("filename", "")).rsplit(SEPARATOR, 1)[0] or "default"
        rect = frame["frame"]
        size = size or [rect["w"], rect["h"]]
        animations.setdefault(tag, []).append([rect["x"], rect["y"]])
    if len(frames) == 1 and list(animations) == ["default"]:
        return None
    return {"frame_size": size, "animations": animations}
