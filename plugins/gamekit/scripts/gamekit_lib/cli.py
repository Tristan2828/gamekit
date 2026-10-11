"""Command line: `python gamekit.py <command>`. Run with -h for the list."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import art, aseprite, credits, manifest, packs, palette, pipeline

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

    pack = commands.add_parser("pack", help="import ready-made asset packs and take assets from them")
    pack_commands = pack.add_subparsers(dest="pack_command", required=True)
    pack_add = pack_commands.add_parser("add", help="copy a downloaded .zip or folder into packs/<name>/")
    pack_add.add_argument("source", help="path to the .zip or folder")
    pack_add.add_argument("name", help="short pack name, e.g. kenney_tiny_dungeon")
    pack_add.add_argument("--url", default="", help="where it was downloaded from")
    _license_args(pack_add)
    pack_license = pack_commands.add_parser("license", help="set a pack's license (from its license file)")
    pack_license.add_argument("name")
    _license_args(pack_license)
    pack_list = pack_commands.add_parser("list", help="list packs, or the files in one pack")
    pack_list.add_argument("name", nargs="?")
    pack_list.add_argument("--filter", default="", help="only paths containing this text")
    pack_info = pack_commands.add_parser("info", help="a pack's license, license files and hints")
    pack_info.add_argument("name")
    pack_use = pack_commands.add_parser("use", help="make an asset from a file in a pack")
    pack_use.add_argument("name", help="pack name")
    pack_use.add_argument("file", help="file inside the pack (as `pack list` shows it)")
    pack_use.add_argument("asset", help="asset id in the manifest")
    pack_use.add_argument("--crop", help="x,y,w,h: cut this part out of the image (or out of a sheet)")
    pack_use.add_argument("--anim", action="append", default=[],
                          help="name=x,y,count: an animation's frames, left to right from x,y (repeatable)")
    pack_use.add_argument("--frame", help="WxH frame size in the pack's sheet (default: the asset's size)")
    pack_use.add_argument("--resize", help="WxH: scale each frame to this size (nearest-neighbor)")
    pack_use.add_argument("--recolor", action="store_true", help="snap colors to the manifest palette")
    pack_use.add_argument("--force", action="store_true", help="overwrite an existing asset file")

    args = parser.parse_args(argv)
    handlers = {"init": _init, "validate": _validate, "status": _status, "credits": _credits,
                "draw": _draw, "export": _export, "check": _check, "preview": _preview, "pack": _pack}
    try:
        return handlers[args.command](args)
    except (manifest.ManifestError, palette.PaletteError, art.ArtError, aseprite.AsepriteError,
            packs.PackError) as error:
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


def _license_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--license", dest="license_name", default="",
                        help="license name exactly as the pack states it, e.g. CC0, CC-BY 4.0")
    parser.add_argument("--author", default="", help="who to credit")
    parser.add_argument("--license-url", default="", help="link to the license or the pack page")


def _pack(args: argparse.Namespace) -> int:
    root = Path(args.manifest).resolve().parent
    return {"add": _pack_add, "license": _pack_license, "list": _pack_list,
            "info": _pack_info, "use": _pack_use}[args.pack_command](args, root)


def _pack_add(args: argparse.Namespace, root: Path) -> int:
    pack = packs.add(root, Path(args.source), args.name)
    pack.source_url = args.url
    if args.license_name or args.author:
        pack.license = {"name": args.license_name, "author": args.author, "url": args.license_url}
    packs.save(pack)
    files = packs.list_files(pack)
    print(f"added pack {pack.name}: {len(files)} files in {pack.files_dir}")
    _print_license(pack)
    print("tip: big packs can be git-ignored (packs/*/files/); keep pack.yaml so the license stays recorded")
    return 0


def _pack_license(args: argparse.Namespace, root: Path) -> int:
    pack = packs.load(root, args.name)
    pack.license = {"name": args.license_name or pack.license.get("name", ""),
                    "author": args.author or pack.license.get("author", ""),
                    "url": args.license_url or pack.license.get("url", "")}
    packs.save(pack)
    _print_license(pack)
    return 0 if pack.has_license() else 1


def _print_license(pack: packs.Pack) -> None:
    if pack.has_license():
        lic = pack.license
        print(f"license: {lic['name']} by {lic['author']}" + (f" ({lic['url']})" if lic.get("url") else ""))
        return
    print("license: NOT SET. Read the pack's license file or download page, then run:")
    print(f'  gamekit pack license {pack.name} --license "<name>" --author "<who to credit>" --license-url <link>')
    hints = packs.license_hints(pack)
    if not hints:
        print("  (no license or readme file found in the pack: check its download page)")
    for rel, found in hints:
        print(f"  {rel}: " + (", ".join(found) if found else "no known license phrases") + " (hints only)")


def _pack_list(args: argparse.Namespace, root: Path) -> int:
    if not args.name:
        found = packs.all_packs(root)
        for pack in found:
            lic = f"{pack.license['name']} by {pack.license['author']}" if pack.has_license() else "license NOT SET"
            print(f"{pack.name}: {len(packs.list_files(pack))} files, {lic}")
        if not found:
            print("no packs yet: import one with `gamekit pack add <zip> <name>`")
        return 0
    pack = packs.load(root, args.name)
    shown = 0
    for rel in packs.list_files(pack):
        suffix = rel.suffix.lower()
        if args.filter.lower() not in rel.as_posix().lower():
            continue
        if suffix in packs.IMAGE_TYPES or suffix in packs.AUDIO_TYPES:
            print(f"{rel.as_posix()}  {packs.describe(pack.files_dir / rel)}")
            shown += 1
    print(f"{shown} image and audio files")
    return 0


def _pack_info(args: argparse.Namespace, root: Path) -> int:
    pack = packs.load(root, args.name)
    print(f"pack {pack.name} ({pack.folder})")
    if pack.source_url:
        print(f"downloaded from: {pack.source_url}")
    _print_license(pack)
    for rel in packs.license_files(pack):
        print(f"license/readme file: {pack.files_dir / rel}")
    return 0


def _size(text: str | None, flag: str) -> tuple[int, int] | None:
    if not text:
        return None
    parts = text.lower().split("x")
    if len(parts) != 2 or not all(p.isdigit() and int(p) > 0 for p in parts):
        raise packs.PackError(f"{flag} needs WxH, e.g. 16x16; got {text!r}")
    return int(parts[0]), int(parts[1])


def _pack_use(args: argparse.Namespace, root: Path) -> int:
    loaded = manifest.load(args.manifest)
    pack = packs.load(root, args.name)
    if not pack.has_license():
        raise packs.PackError(f"pack {pack.name} has no license recorded yet; run `gamekit pack info {pack.name}`")
    by_id = {a.id: a for a in loaded.assets}
    if args.asset not in by_id:
        raise packs.PackError(f"{args.asset!r} is not in {args.manifest}")
    asset = by_id[args.asset]
    source = packs.resolve(pack, args.file)
    out = loaded.asset_path(asset)
    if out.exists() and not args.force:
        raise packs.PackError(f"{out} already exists; add --force to replace it")
    out_suffix = out.suffix.lower()

    if out_suffix in (".wav", ".ogg"):
        if source.suffix.lower() != out_suffix:
            raise packs.PackError(f"{source.name} is {source.suffix}, the asset wants {out_suffix}; "
                                  "convert it first (the sound clean-up step does this)")
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, out)
        print(f"{asset.id}: copied {pack.name}/{args.file} -> {asset.file}")
    elif out_suffix == ".png":
        if source.suffix.lower() not in packs.IMAGE_TYPES:
            raise packs.PackError(f"{source.name} is not an image")
        asset_size = tuple(asset.size) if isinstance(asset.size, list) and len(asset.size) == 2 else None
        anims = [packs.parse_anim(a) for a in args.anim]
        frame = _size(args.frame, "--frame") or asset_size
        crop_box = packs.parse_box(args.crop) if args.crop else None
        image, sidecar = packs.build(source, crop_box, anims, frame, _size(args.resize, "--resize"))
        if args.recolor:
            image, changed = packs.recolor(image, [e.color for e in pipeline.palette_entries(loaded)])
            print(f"recolored {changed} pixels to the palette")
        art.save(image, sidecar, out)
        print(f"{asset.id}: {pack.name}/{args.file} -> {asset.file}")
        problems = pipeline.check(loaded, asset, [e.color for e in pipeline.palette_entries(loaded)])
        for problem in problems:
            print(f"  - {problem}")
    else:
        raise packs.PackError(f"{asset.id}: don't know how to make a {out_suffix} file from a pack")

    if asset.source != "pack" or asset.license.get("pack") != pack.name or asset.status == "todo":
        print(f"now update {asset.id} in {Path(args.manifest).name}:")
        print(f"  source: pack, status: draft, license: {{pack: {pack.name}}}")
    return 0
