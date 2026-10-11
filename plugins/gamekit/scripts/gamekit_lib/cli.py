"""Command line: `python gamekit.py <command>`. Run with -h for the list."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import credits, manifest, palette

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

    args = parser.parse_args(argv)
    try:
        return {"init": _init, "validate": _validate, "status": _status, "credits": _credits}[args.command](args)
    except (manifest.ManifestError, palette.PaletteError) as error:
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
