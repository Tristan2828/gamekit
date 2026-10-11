"""A game's palette: the fixed set of colors every sprite should use.

Accepts two formats:
- .hex: one RRGGBB color per line (Lospec's "HEX file" download); '#' prefixes,
  blank lines and lines starting with ';' or '//' are ignored.
- .gpl: a GIMP / Aseprite palette ("GIMP Palette" header, then "R G B name" rows).
"""
from __future__ import annotations

import re
from pathlib import Path

HEX_LINE = re.compile(r"^#?([0-9a-fA-F]{6})\b")


class PaletteError(Exception):
    pass


def load(path: str | Path) -> list[tuple[int, int, int]]:
    path = Path(path)
    if not path.exists():
        raise PaletteError(f"{path} not found")
    lines = path.read_text(encoding="utf-8").splitlines()
    colors = _parse_gpl(lines) if lines and lines[0].strip() == "GIMP Palette" else _parse_hex(lines, path)
    if not colors:
        raise PaletteError(f"{path} has no colors")
    return colors


def _parse_hex(lines: list[str], path: Path) -> list[tuple[int, int, int]]:
    colors: list[tuple[int, int, int]] = []
    for n, line in enumerate(lines, start=1):
        line = line.strip()
        if not line or line.startswith((";", "//")):
            continue
        match = HEX_LINE.match(line)
        if not match:
            raise PaletteError(f"{path}:{n}: expected a RRGGBB color, got {line!r}")
        value = match.group(1)
        colors.append((int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)))
    return colors


def _parse_gpl(lines: list[str]) -> list[tuple[int, int, int]]:
    colors: list[tuple[int, int, int]] = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
            colors.append((int(parts[0]), int(parts[1]), int(parts[2])))
    return colors


def to_hex(color: tuple[int, int, int]) -> str:
    return "{:02x}{:02x}{:02x}".format(*color)
