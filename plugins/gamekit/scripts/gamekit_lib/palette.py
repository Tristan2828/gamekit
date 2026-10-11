"""A game's palette: the fixed set of colors every sprite should use.

Accepts two formats:
- .hex: one RRGGBB color per line (Lospec's "HEX file" download); '#' prefixes,
  blank lines and lines starting with ';' or '//' are ignored. Text after the color
  on the same line is its name (e.g. "0d0b12 k").
- .gpl: a GIMP / Aseprite palette ("GIMP Palette" header, then "R G B name" rows).

Single-character names double as drawing keys for text-row sprites (see art.py),
so a palette named "k", "w", "r"... can be drawn with directly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

Color = tuple[int, int, int]
HEX_LINE = re.compile(r"^#?([0-9a-fA-F]{6})\b\s*(.*)$")


@dataclass
class Entry:
    color: Color
    name: str = ""


class PaletteError(Exception):
    pass


def load(path: str | Path) -> list[Color]:
    return [e.color for e in load_entries(path)]


def load_entries(path: str | Path) -> list[Entry]:
    path = Path(path)
    if not path.exists():
        raise PaletteError(f"{path} not found")
    lines = path.read_text(encoding="utf-8").splitlines()
    entries = _parse_gpl(lines) if lines and lines[0].strip() == "GIMP Palette" else _parse_hex(lines, path)
    if not entries:
        raise PaletteError(f"{path} has no colors")
    return entries


def keys(entries: list[Entry]) -> dict[str, Color]:
    """Single-character color names, usable as drawing keys."""
    return {e.name: e.color for e in entries if len(e.name) == 1 and e.name != "."}


def _parse_hex(lines: list[str], path: Path) -> list[Entry]:
    entries: list[Entry] = []
    for n, line in enumerate(lines, start=1):
        line = line.strip()
        if not line or line.startswith((";", "//")):
            continue
        match = HEX_LINE.match(line)
        if not match:
            raise PaletteError(f"{path}:{n}: expected a RRGGBB color, got {line!r}")
        entries.append(Entry(parse_hex(match.group(1)), match.group(2).strip()))
    return entries


def _parse_gpl(lines: list[str]) -> list[Entry]:
    entries: list[Entry] = []
    for line in lines[1:]:
        parts = line.split(None, 3)
        if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
            name = parts[3].strip() if len(parts) > 3 else ""
            entries.append(Entry((int(parts[0]), int(parts[1]), int(parts[2])), name))
    return entries


def parse_hex(value: str) -> Color:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def to_hex(color: Color) -> str:
    return "{:02x}{:02x}{:02x}".format(*color[:3])
