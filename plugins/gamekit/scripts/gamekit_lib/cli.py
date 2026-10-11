"""Command line: `python gamekit.py <command>`. Run with -h for the list."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import art, aseprite, credits, manifest, palette, pipeline

TEMPLATES = Path(__file__).resolve().parent.parent.parent / "templates"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gamekit", description="Game asset manifest tools.")
    parser.add_argument("-m", "--manifest", default="assets.yaml",
                        help="path to the manifest (default: ./assets.yaml)")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create assets.yaml and palette.hex if missing")
    init.add_argument("--game", default="", help="game name written into the manifest")

    validate = commands.add_parser("validate", help="check the manifest for mistakes")
    validate.add_argument("--no-files", action="store_true", help="skip checking that done assets exist")

    status = commands.add_parser("status", help="progress per kind, and what's left")
    status.add_argument("--todo", action="store_true", help="also list every unfinished asset")

    write_credits = commands.add_parser("credits", help="write CREDITS.md from the manifest")
    write_credits.add_argument("-o", "--out", default="CREDITS.md", help="output path (default: ./CREDITS.md)")

    draw = commands.add_parser("draw", help="render Claude's text sprites (art/<id>.yaml) to PNG")
    draw.add_argument("ids", nargs="*", help="asset ids (default: every source: claude asset with a source file)")

    export = commands.add_parser("export", help="export .aseprite files with the Aseprite CLI")
    export.add_argument("ids", nargs="*", help="asset ids (default: every source: self asset with a source file)")

    check = commands.add_parser("check", help="check finished images: size, frames, palette")
    check.add_argument("ids", nargs="*", help="asset ids (default: every image asset whose file exists)")

    show = commands.add_parser("preview", help="write a scaled-up contact sheet of finished images")
    show.add_argument("ids", nargs="*", help="asset ids (default: every image asset whose file exists)")
    show.add_argument("-o", "--out", default="preview.png", help="output path (default: ./preview.png)")
    show.add_argument("--scale", type=int, default=4, help="pixel scale (default: 4)")
    show.add_argument("--columns", type=int, default=6, help="images per row (default: 6)")

    args = parser.parse_args(argv)
    handlers = {"init": _init, "validate": _validate, "status": _status, "credits": _credits,
                "draw": _draw, "export": _export, "check": _check, "preview": _preview}
    try:
        return handlers[args.command](args)
    except (manifest.ManifestError, palette.PaletteError, art.ArtError, aseprite.AsepriteError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _init(args: argparse.Namespace) -> int:
    path = Path(args.manifest)
    if path.exists():
        print(f"{path} already exists; left it alone.")
    else:
        text = (TEMPLATES / "assets.yaml").read_text(encoding="utf-8")
        path.write_text(text.replace("game: My Game", f"game: {args.game or path.resolve().parent.name}"),
                        encoding="utf-8")
        print(f"created {path}")
    palette_path = path.parent / "palette.hex"
    if palette_path.exists():
        print(f"{palette_path} already exists; left it alone.")
    else:
        shutil.copyfile(TEMPLATES / "palette.hex", palette_path)
        print(f"created {palette_path} (replace it with your game's palette)")
    return 0


def _validate(args: argparse.Namespace) -> int:
    loaded = manifest.load(args.manifest)
    problems = manifest.validate(loaded, check_files=not args.no_files)
    if loaded.palette:
        try:
            colors = palette.load(loaded.root / loaded.palette)
            print(f"palette: {len(colors)} colors from {loaded.palette}")
        except palette.PaletteError as error:
            problems.append(f"palette: {error}")
    for problem in problems:
        print(f"- {problem}")
    if problems:
        print(f"{len(problems)} problem{'s' if len(problems) != 1 else ''} in {args.manifest}")
        return 1
    print(f"{args.manifest}: {len(loaded.assets)} assets, no problems")
    return 0


def _status(args: argparse.Namespace) -> int:
    loaded = manifest.load(args.manifest)
    table = manifest.summary(loaded)
    header = f"{'kind':<10}{'todo':>6}{'draft':>7}{'done':>6}{'total':>7}{'images':>8}"
    print(f"{loaded.game or args.manifest}")
    print(header)
    print("-" * len(header))
    totals = {"todo": 0, "draft": 0, "done": 0, "frames": 0}
    for kind in manifest.KINDS:
        if kind not in table:
            continue
        row = table[kind]
        total = row["todo"] + row["draft"] + row["done"]
        images = str(row["frames"]) if row["frames"] else "-"
        print(f"{kind:<10}{row['todo']:>6}{row['draft']:>7}{row['done']:>6}{total:>7}{images:>8}")
        for key in totals:
            totals[key] += row[key]
    count = totals["todo"] + totals["draft"] + totals["done"]
    print("-" * len(header))
    print(f"{'all':<10}{totals['todo']:>6}{totals['draft']:>7}{totals['done']:>6}{count:>7}{totals['frames']:>8}")
    if count:
        print(f"{round(100 * totals['done'] / count)}% done")
    if args.todo:
        unfinished = [a for a in loaded.assets if a.status != "done"]
        if unfinished:
            print("\nunfinished:")
            for a in unfinished:
                size = f" {a.size[0]}x{a.size[1]}" if isinstance(a.size, list) and len(a.size) == 2 else ""
                frames = (" frames " + ", ".join(f"{name} {n}" for name, n in a.frames.items())
                          if isinstance(a.frames, dict) and a.frames else "")
                print(f"- [{a.status}] {a.kind} {a.id}{size}{frames} ({a.source}) -> {a.file}")
    return 0


def _credits(args: argparse.Namespace) -> int:
    loaded = manifest.load(args.manifest)
    Path(args.out).write_text(credits.render(loaded), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


def _sources(loaded: manifest.Manifest, ids: list[str], source: str) -> list[manifest.Asset]:
    """Assets to build: the named ones, or every `source` asset whose source file exists."""
    if ids:
        return pipeline.image_assets(loaded, ids)
    picked = []
    for a in loaded.assets:
        src = loaded.source_path(a)
        if a.source == source and src is not None and src.exists():
            picked.append(a)
    return picked


def _report(results: list[tuple[manifest.Asset, list[str]]], verb: str) -> int:
    failed = 0
    for asset, problems in results:
        if problems:
            failed += 1
            print(f"{asset.id}: {verb}, with problems:")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print(f"{asset.id}: {verb} -> {asset.file}")
    if not results:
        print("nothing to do")
    return 1 if failed else 0


def _draw(args: argparse.Namespace) -> int:
    loaded = manifest.load(args.manifest)
    results = [(a, pipeline.draw(loaded, a)) for a in _sources(loaded, args.ids, "claude")]
    return _report(results, "drawn")


def _export(args: argparse.Namespace) -> int:
    loaded = manifest.load(args.manifest)
    assets = _sources(loaded, args.ids, "self")
    exe = aseprite.find() if assets else None
    results = [(a, pipeline.export(loaded, a, exe)) for a in assets]
    return _report(results, "exported")


def _check(args: argparse.Namespace) -> int:
    loaded = manifest.load(args.manifest)
    colors = [e.color for e in pipeline.palette_entries(loaded)]
    assets = pipeline.image_assets(loaded, args.ids)
    if not args.ids:
        assets = [a for a in assets if loaded.asset_path(a).exists()]
    problems = [p for a in assets for p in pipeline.check(loaded, a, colors)]
    for problem in problems:
        print(f"- {problem}")
    print(f"checked {len(assets)} image{'s' if len(assets) != 1 else ''}: "
          f"{len(problems) or 'no'} problem{'s' if len(problems) != 1 else ''}")
    return 1 if problems else 0


def _preview(args: argparse.Namespace) -> int:
    loaded = manifest.load(args.manifest)
    items = pipeline.preview_items(loaded, pipeline.image_assets(loaded, args.ids))
    art.preview(items, scale=max(1, args.scale), columns=max(1, args.columns)).save(args.out)
    print(f"wrote {args.out} ({len(items)} images)")
    return 0
