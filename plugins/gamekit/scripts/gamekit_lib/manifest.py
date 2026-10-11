"""The asset manifest (assets.yaml): one entry per asset a game needs.

Every gamekit tool reads this file, and the skills keep it up to date, so it
always answers "what exists, what's missing, and where did it come from".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

KINDS = {
    # kind: (file extensions allowed, needs a pixel size)
    "sprite": ({".png"}, True),
    "tileset": ({".png"}, True),
    "icon": ({".png"}, True),
    "ui": ({".png"}, True),
    "font": ({".png", ".ttf", ".otf"}, False),
    "sfx": ({".wav"}, False),
    "music": ({".ogg"}, False),
}
SOURCES = {
    "claude": "drawn by Claude (text rows)",
    "self": "made by you",
    "pack": "ready-made art pack",
    "library": "sound library (Freesound, Kenney, Sonniss...)",
    "sfxr": "procedural sound effect",
    "synth": "rendered from a text score",
    "commission": "made by a hired artist or composer",
}
# Sources that need a license entry before the asset counts as usable.
LICENSED_SOURCES = {"pack", "library", "commission"}
STATUSES = ["todo", "draft", "done"]
# Where each source's editable file lives unless an asset sets `src`.
DEFAULT_SOURCES = {"claude": "art/{id}.yaml", "self": "art/{id}.aseprite", "sfxr": "sounds/{id}.yaml"}
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]*$")


@dataclass
class Asset:
    id: str
    kind: str
    source: str
    status: str = "todo"
    file: str = ""
    size: list[int] | None = None
    frames: dict[str, int] = field(default_factory=dict)
    replaces: str = ""
    src: str = ""
    loop: bool | None = None
    license: dict[str, str] = field(default_factory=dict)
    notes: str = ""

    def frame_count(self) -> int:
        """Images to make: the animation frames, or 1 for a still image, 0 for audio."""
        if self.frames:
            return sum(self.frames.values())
        _, has_pixels = KINDS.get(self.kind, (set(), False))
        return 1 if has_pixels else 0


@dataclass
class Manifest:
    path: Path
    game: str
    output: str
    palette: str
    assets: list[Asset]
    music: dict = field(default_factory=dict)

    @property
    def root(self) -> Path:
        return self.path.parent

    def output_dir(self) -> Path:
        return self.root / self.output

    def asset_path(self, asset: Asset) -> Path:
        return self.output_dir() / asset.file

    def loops(self, asset: Asset) -> bool:
        """Music loops unless it says `loop: false`."""
        return asset.kind == "music" and asset.loop is not False

    def track_name(self, asset: Asset) -> str:
        """The name the game's render script knows a track by."""
        return asset.replaces or asset.id

    def source_path(self, asset: Asset) -> Path | None:
        """The editable source file: `src` if set, else the default for the asset's source (DEFAULT_SOURCES)."""
        if asset.src:
            return self.root / asset.src
        default = DEFAULT_SOURCES.get(asset.source)
        return self.root / default.format(id=asset.id) if default else None


class ManifestError(Exception):
    pass


def load(path: str | Path) -> Manifest:
    path = Path(path)
    if not path.exists():
        raise ManifestError(f"{path} not found. Run `gamekit init` first.")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ManifestError(f"{path}: expected a mapping at the top level")
    raw_assets = data.get("assets") or []
    if not isinstance(raw_assets, list):
        raise ManifestError(f"{path}: 'assets' must be a list")
    assets: list[Asset] = []
    for i, raw in enumerate(raw_assets):
        if not isinstance(raw, dict):
            raise ManifestError(f"{path}: assets[{i}] must be a mapping")
        assets.append(_asset_from_dict(raw))
    return Manifest(
        path=path,
        game=str(data.get("game", "")),
        output=str(data.get("output", "assets")),
        palette=str(data.get("palette", "") or ""),
        assets=assets,
        music=dict(data.get("music") or {}) if isinstance(data.get("music") or {}, dict) else {"_bad": True},
    )


def _asset_from_dict(raw: dict) -> Asset:
    size = raw.get("size")
    frames = raw.get("frames") or {}
    return Asset(
        id=str(raw.get("id", "")),
        kind=str(raw.get("kind", "")),
        source=str(raw.get("source", "")),
        status=str(raw.get("status", "todo")),
        file=str(raw.get("file", "") or ""),
        size=list(size) if isinstance(size, list) else size,
        frames=dict(frames) if isinstance(frames, dict) else frames,
        replaces=str(raw.get("replaces", "") or ""),
        src=str(raw.get("src", "") or ""),
        loop=raw.get("loop"),
        license=dict(raw.get("license") or {}),
        notes=str(raw.get("notes", "") or ""),
    )


def validate(manifest: Manifest, check_files: bool = True) -> list[str]:
    """Returns a list of problems; empty means the manifest is valid."""
    problems: list[str] = []
    if manifest.music.get("_bad"):
        problems.append("music: must be a mapping (godot_project, render_script)")
    elif set(manifest.music) - {"godot_project", "render_script"}:
        problems.append(f"music: unknown keys {sorted(set(manifest.music) - {'godot_project', 'render_script'})}")
    seen: set[str] = set()
    for i, a in enumerate(manifest.assets):
        where = f"assets[{i}] ({a.id or 'no id'})"
        if not ID_PATTERN.match(a.id):
            problems.append(f"{where}: id must be lowercase snake_case")
        elif a.id in seen:
            problems.append(f"{where}: duplicate id")
        seen.add(a.id)

        if a.kind not in KINDS:
            problems.append(f"{where}: kind must be one of {', '.join(KINDS)}")
            continue
        if a.source not in SOURCES:
            problems.append(f"{where}: source must be one of {', '.join(SOURCES)}")
        if a.status not in STATUSES:
            problems.append(f"{where}: status must be one of {', '.join(STATUSES)}")

        extensions, needs_size = KINDS[a.kind]
        if not a.file:
            problems.append(f"{where}: file is required (path inside '{manifest.output}/')")
        elif Path(a.file).suffix.lower() not in extensions:
            problems.append(f"{where}: a {a.kind} file must end in {' or '.join(sorted(extensions))}")
        if needs_size:
            if not (isinstance(a.size, list) and len(a.size) == 2
                    and all(isinstance(n, int) and n > 0 for n in a.size)):
                problems.append(f"{where}: size must be [width, height] in pixels")
        elif a.size is not None:
            problems.append(f"{where}: a {a.kind} has no pixel size")
        if not isinstance(a.frames, dict) or not all(
                isinstance(k, str) and isinstance(v, int) and v > 0 for k, v in a.frames.items()):
            problems.append(f"{where}: frames must map animation name -> frame count, e.g. {{walk: 4}}")
        elif a.frames and a.kind != "sprite":
            problems.append(f"{where}: only sprites have animation frames")

        if a.loop is not None and (not isinstance(a.loop, bool) or a.kind != "music"):
            problems.append(f"{where}: loop is true / false, for music only")

        if a.source in LICENSED_SOURCES and a.status != "todo":
            try:
                lic = effective_license(manifest, a)
            except Exception as error:  # a missing or broken pack.yaml
                problems.append(f"{where}: license.pack: {error}")
            else:
                if not lic.get("name"):
                    problems.append(f"{where}: a {a.source} asset needs license.name (e.g. CC0, CC-BY 4.0)"
                                    + (" in its pack.yaml" if a.license.get("pack") else ""))
                if not lic.get("author"):
                    problems.append(f"{where}: a {a.source} asset needs license.author"
                                    + (" in its pack.yaml" if a.license.get("pack") else ""))
        if check_files and a.status == "done" and a.file and not manifest.asset_path(a).exists():
            problems.append(f"{where}: marked done but {manifest.output}/{a.file} is missing")
    return problems


def summary(manifest: Manifest) -> dict[str, dict[str, int]]:
    """Counts per kind and status, plus total frames per kind."""
    table: dict[str, dict[str, int]] = {}
    for a in manifest.assets:
        row = table.setdefault(a.kind, {s: 0 for s in STATUSES} | {"frames": 0})
        if a.status in row:
            row[a.status] += 1
        if isinstance(a.frames, dict):
            row["frames"] += a.frame_count()
    return table


def effective_license(manifest: Manifest, asset: Asset) -> dict[str, str]:
    """The asset's license; `license: {pack: <name>}` reads it from packs/<name>/pack.yaml."""
    pack_name = asset.license.get("pack")
    if not pack_name:
        return asset.license
    from . import packs  # here to avoid importing Pillow for plain manifest checks
    pack = packs.load(manifest.root, str(pack_name))
    return {**pack.license, **{k: v for k, v in asset.license.items() if k != "pack"}}
