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
    "voice": ({".wav"}, False),
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
    "ai": "made with a local AI model (gamekit engines)",
}
# Sources that need a license entry before the asset counts as usable.
LICENSED_SOURCES = {"pack", "library", "commission"}
STATUSES = ["todo", "draft", "done", "keep"]
# Finished statuses. keep = the game's own version (made by its code: text sprites, synth sounds) stays, by choice.
FINISHED = ("done", "keep")
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
    unknown: list[str] = field(default_factory=list, compare=False)  # keys gamekit doesn't know (typos?)

    def frame_count(self) -> int:
        """Images to make: the animation frames, or 1 for a still image, 0 for audio."""
        if isinstance(self.frames, dict) and self.frames:
            return sum(_count(n) for n in self.frames.values())
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
    frame_files: bool = False
    audio: dict = field(default_factory=dict)
    code_art: str = ""
    sprites: dict = field(default_factory=dict)  # the game's sprite rules: prompt, outline, reserved_colors
    load_problems: list[str] = field(default_factory=list)  # found while reading; validate reports them

    @property
    def outline(self) -> str | None:
        """sprites.outline when it's a color (validate reports a bad one)."""
        value = self.sprites.get("outline")
        return value if isinstance(value, str) and HEX_PATTERN.match(value) else None

    @property
    def reserved_colors(self) -> list[str]:
        """sprites.reserved_colors that are colors (validate reports bad ones)."""
        value = self.sprites.get("reserved_colors") or []
        return [c for c in value if isinstance(c, str) and HEX_PATTERN.match(c)] if isinstance(value, list) else []

    @property
    def sfx_peak_db(self) -> float:
        value = self.audio.get("sfx_peak_db", -1.0)
        return float(value) if _number(value) else -1.0  # a bad value is reported by validate

    @property
    def music_lufs(self) -> float | None:
        value = self.audio.get("music_lufs")
        return float(value) if _number(value) else None

    def frame_paths(self, asset: Asset) -> list[tuple[str, int, Path]]:
        """With `frame_files: true`, each animation frame is its own PNG next to the asset's file:
        idle frame 0 is the file itself, more idle frames are <name>_1, <name>_2...; another
        animation's frames are <name>_<anim>_1, _2... (<name>_<anim> when it has one frame).
        Empty when the asset is a single image or a sheet."""
        if not (self.frame_files and asset.kind == "sprite" and isinstance(asset.frames, dict) and asset.frames):
            return []
        base = self.asset_path(asset)
        return [(anim, i, base.parent / f"{name}.png") for anim, i, name in frame_names(asset, base.stem)]

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


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _count(value: object) -> int:
    """A frame count as written, or 0 when it isn't a whole number (validate reports it)."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def frame_names(asset: Asset, stem: str) -> list[tuple[str, int, str]]:
    """(animation, index, name) per frame: idle frame 0 is `stem`, more idle frames `stem_1`, `stem_2`...;
    another animation's frames `stem_<anim>_1`, `_2`... (`stem_<anim>` when it has one frame).
    A still image is just `stem`."""
    frames = asset.frames if isinstance(asset.frames, dict) and asset.frames else {"idle": 1}
    names = []
    for anim, count in frames.items():
        count = _count(count)
        for i in range(count):
            if anim == "idle":
                name = stem if i == 0 else f"{stem}_{i}"
            elif count == 1:
                name = f"{stem}_{anim}"
            else:
                name = f"{stem}_{anim}_{i + 1}"
            names.append((anim, i, name))
    return names


class ManifestError(Exception):
    pass


def load(path: str | Path) -> Manifest:
    path = Path(path).absolute()  # its paths go to AI workers, which run in their own folder
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
    known = {"game", "output", "palette", "assets", "music", "frame_files", "audio", "code_art", "sprites"}
    load_problems = [f"unknown setting {key!r} (a typo? see the field reference in gamekit's templates/assets.yaml)"
                     for key in data if key not in known]
    if not isinstance(data.get("frame_files", False), bool):
        load_problems.append(f"frame_files: true or false, got {data.get('frame_files')!r}")
    return Manifest(
        path=path,
        game=str(data.get("game", "")),
        output=str(data.get("output", "assets")),
        palette=str(data.get("palette", "") or ""),
        assets=assets,
        music=dict(data.get("music") or {}) if isinstance(data.get("music") or {}, dict) else {"_bad": True},
        frame_files=data.get("frame_files", False) is True,
        audio=dict(data.get("audio") or {}) if isinstance(data.get("audio") or {}, dict) else {"_bad": True},
        code_art=str(data.get("code_art") or ""),
        sprites=dict(data.get("sprites") or {}) if isinstance(data.get("sprites") or {}, dict) else {"_bad": True},
        load_problems=load_problems,
    )


ASSET_KEYS = {"id", "kind", "source", "status", "file", "size", "frames", "replaces", "src", "loop", "license", "notes"}


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
        license=dict(lic) if isinstance(lic := raw.get("license") or {}, dict) else {"_bad": str(lic)},
        notes=str(raw.get("notes", "") or ""),
        unknown=[str(k) for k in raw if k not in ASSET_KEYS],
    )


HEX_PATTERN = re.compile(r"^#?[0-9a-fA-F]{6}$")


def _sprite_rule_problems(rules: dict) -> list[str]:
    if rules.get("_bad"):
        return ["sprites: must be a mapping (prompt, outline, reserved_colors, game_scale, floors)"]
    problems = []
    unknown = set(rules) - {"prompt", "outline", "reserved_colors", "game_scale", "floors"}
    if unknown:
        problems.append(f"sprites: unknown keys {sorted(unknown)}")
    if "prompt" in rules and not isinstance(rules["prompt"], str):
        problems.append("sprites.prompt: text")
    if "outline" in rules and not (isinstance(rules["outline"], str) and HEX_PATTERN.match(rules["outline"])):
        problems.append(f"sprites.outline: a color like \"#17121C\", got {rules['outline']!r}")
    reserved = rules.get("reserved_colors", [])
    if not (isinstance(reserved, list) and all(isinstance(c, str) and HEX_PATTERN.match(c) for c in reserved)):
        problems.append("sprites.reserved_colors: a list of colors like \"#FF00FF\"")
    scale = rules.get("game_scale", 3)
    if not (isinstance(scale, int) and not isinstance(scale, bool) and 1 <= scale <= 12):
        problems.append(f"sprites.game_scale: a whole number from 1 to 12, got {scale!r}")
    floors = rules.get("floors", {})
    if not (isinstance(floors, dict) and all(isinstance(c, str) and HEX_PATTERN.match(c) for c in floors.values())):
        problems.append("sprites.floors: names and colors, e.g. {The Crypt: \"#1C1A21\"}")
    return problems


def validate(manifest: Manifest, check_files: bool = True) -> list[str]:
    """Returns a list of problems; empty means the manifest is valid."""
    problems: list[str] = list(manifest.load_problems)
    if manifest.music.get("_bad"):
        problems.append("music: must be a mapping (godot_project, render_script)")
    elif set(manifest.music) - {"godot_project", "render_script"}:
        problems.append(f"music: unknown keys {sorted(set(manifest.music) - {'godot_project', 'render_script'})}")
    if manifest.audio.get("_bad"):
        problems.append("audio: must be a mapping (sfx_peak_db, music_lufs)")
    else:
        unknown = set(manifest.audio) - {"sfx_peak_db", "music_lufs"}
        if unknown:
            problems.append(f"audio: unknown keys {sorted(unknown)}")
        for key in ("sfx_peak_db", "music_lufs"):
            value = manifest.audio.get(key)
            if value is not None and (not isinstance(value, (int, float)) or value > 0):
                problems.append(f"audio.{key}: a negative number (dB), got {value!r}")
    problems += _sprite_rule_problems(manifest.sprites)
    if manifest.code_art and not (manifest.root / manifest.code_art).is_file():
        problems.append(f"code_art: {manifest.code_art} not found")
    seen: set[str] = set()
    for i, a in enumerate(manifest.assets):
        where = f"assets[{i}] ({a.id or 'no id'})"
        if not ID_PATTERN.match(a.id):
            problems.append(f"{where}: id must be lowercase snake_case")
        elif a.id in seen:
            problems.append(f"{where}: duplicate id")
        seen.add(a.id)

        if a.unknown:
            problems.append(f"{where}: unknown keys {', '.join(a.unknown)} (typos? known: {', '.join(sorted(ASSET_KEYS))})")
        if a.license.get("_bad"):
            problems.append(f"{where}: license must be {{name, author, url}} or {{pack: <name>}}, "
                            f"not {a.license['_bad']!r}")
        if a.src and Path(a.src).is_absolute():
            problems.append(f"{where}: src must be a path inside the game folder, not {a.src}")
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
        good_size = isinstance(a.size, list) and len(a.size) == 2 and all(
            isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in a.size)
        if needs_size or a.kind == "font" and a.size is not None:  # a pixel font may give its glyph size
            if not good_size:
                problems.append(f"{where}: size must be [width, height] in pixels")
        elif a.size is not None:
            problems.append(f"{where}: a {a.kind} has no pixel size")
        if not isinstance(a.frames, dict) or not all(
                isinstance(k, str) and _count(v) for k, v in a.frames.items()):
            problems.append(f"{where}: frames must map animation name -> frame count, e.g. {{walk: 4}}")
        elif a.frames and a.kind != "sprite":
            problems.append(f"{where}: only sprites have animation frames")
        elif a.frames and manifest.frame_files and "idle" not in a.frames:
            problems.append(f"{where}: with frame_files, frames need an idle animation (its first frame is the file itself)")

        if a.loop is not None and (not isinstance(a.loop, bool) or a.kind != "music"):
            problems.append(f"{where}: loop is true / false, for music only")

        if a.source in LICENSED_SOURCES and a.status not in ("todo", "keep"):
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


def set_status(path: str | Path, asset_id: str, status: str) -> None:
    """Changes one asset's status in assets.yaml in place (see set_fields)."""
    if status not in STATUSES:
        raise ManifestError(f"status must be one of {', '.join(STATUSES)}")
    set_fields(path, asset_id, {"status": status})


PACK_LICENSE = re.compile(r"\{pack: [a-z0-9][a-z0-9_-]*\}")
VALUE = r"(\{[^{}]*\}|[\w-]+)"  # a field's current value on its line: a word or a one-line {...}


def set_fields(path: str | Path, asset_id: str, values: dict[str, str]) -> None:
    """Changes simple fields (status, source...) of one asset in assets.yaml in place, keeping every
    comment and the layout. Works for one-line entries (`- {id: hero, status: todo, ...}`) and block
    entries (`- id: hero` with the fields on the lines below). Missing fields are added after the id.
    Besides simple words, `license` can be set to `{pack: <name>}` (an asset taken from a pack)."""
    for key, value in values.items():
        simple = re.fullmatch(r"[a-z0-9_]+", str(value)) or (key == "license" and PACK_LICENSE.fullmatch(str(value)))
        if not re.fullmatch(r"[a-z_]+", key) or not simple:
            raise ManifestError(f"can't write {key}: {value!r} (only simple words)")
    path = Path(path)
    text = path.read_bytes().decode("utf-8")  # bytes, so the file keeps its own line endings
    lines = text.splitlines(keepends=True)
    name = re.escape(asset_id)
    id_part = r"\bid:\s*[\"']?" + name + r"[\"']?"
    flow = re.compile(r"^\s*-\s*\{.*" + id_part + r"\s*[,}]")
    flow_first = re.compile(r"^\s*-\s*\{\s*" + id_part + r"\s*[,}]")  # id as the first key: never inside notes
    block = re.compile(r"^(\s*)-\s+id:\s*[\"']?" + name + r"[\"']?\s*(#.*)?$")
    if any(flow_first.match(line) for line in lines):
        flow = flow_first
    for i, line in enumerate(lines):
        if flow.match(line):
            for key, value in values.items():
                if re.search(rf"\b{key}:\s*{VALUE}", line):
                    line = re.sub(rf"\b{key}:\s*{VALUE}", lambda _: f"{key}: {value}", line, count=1)
                else:
                    line = re.sub("(" + id_part + ")", rf"\1, {key}: {value}", line, count=1)
            lines[i] = line
            break
        found = block.match(line.rstrip("\r\n"))
        if found:
            indent = len(found.group(1))
            end = i + 1
            while end < len(lines) and (not lines[end].strip() or len(lines[end]) - len(lines[end].lstrip()) > indent):
                end += 1
            newline = "\r\n" if line.endswith("\r\n") else "\n"
            for key, value in values.items():
                for j in range(i + 1, end):
                    if re.match(rf"^\s+{key}:", lines[j]):
                        field_indent = len(lines[j]) - len(lines[j].lstrip())
                        if re.match(rf"^\s+{key}:\s*(#.*)?$", lines[j]):  # a nested block (license:, then name: ...)
                            lines[j] = " " * field_indent + f"{key}: {value}" + newline
                            while j + 1 < end and lines[j + 1].strip() and \
                                    len(lines[j + 1]) - len(lines[j + 1].lstrip()) > field_indent:
                                del lines[j + 1]
                                end -= 1
                        else:
                            lines[j] = re.sub(rf"({key}:\s*){VALUE}", lambda m: m.group(1) + value, lines[j], count=1)
                        break
                else:
                    lines.insert(i + 1, " " * (indent + 2) + f"{key}: {value}" + newline)
                    end += 1
            break
    else:
        raise ManifestError(f"{asset_id!r} is not in {path.name}")
    changed = "".join(lines)
    before = {a.id: a for a in _parse(text, path)}
    check = {a.id: a for a in _parse(changed, path)}
    others_same = check.keys() == before.keys() and all(
        check[i] == a for i, a in before.items() if i != asset_id)
    rest_same = asset_id in check and all(getattr(check[asset_id], f) == getattr(before[asset_id], f)
                                          for f in vars(before[asset_id]) if f not in values)
    if not others_same or not rest_same or any(_written(check[asset_id], k) != str(v) for k, v in values.items()):
        # never write a file we can't read back the way we meant, or that changes anything else
        raise ManifestError(f"couldn't change {asset_id} safely; edit {path.name} by hand")
    path.write_bytes(changed.encode("utf-8"))


def _written(asset: Asset, key: str) -> str:
    """A field as set_fields writes it, to check that the file reads back the way it was meant."""
    if key == "license":
        return "{pack: " + str(asset.license.get("pack")) + "}" if set(asset.license) == {"pack"} else str(asset.license)
    return str(getattr(asset, key, None))


def _parse(text: str, path: Path) -> list[Asset]:
    data = yaml.safe_load(text) or {}
    raw_assets = data.get("assets") if isinstance(data, dict) else None
    if not isinstance(raw_assets, list):
        raise ManifestError(f"{path}: 'assets' must be a list")
    return [_asset_from_dict(raw) for raw in raw_assets if isinstance(raw, dict)]


def effective_license(manifest: Manifest, asset: Asset) -> dict[str, str]:
    """The asset's license; `license: {pack: <name>}` reads it from packs/<name>/pack.yaml."""
    pack_name = asset.license.get("pack")
    if not pack_name:
        return asset.license
    from . import packs  # here to avoid importing Pillow for plain manifest checks
    pack = packs.load(manifest.root, str(pack_name))
    return {**pack.license, **{k: v for k, v in asset.license.items() if k != "pack"}}
