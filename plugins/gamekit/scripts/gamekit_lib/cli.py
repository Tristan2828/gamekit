"""Command line: `python gamekit.py <command>`. Run with -h for the list."""
from __future__ import annotations

import argparse
import random
import shutil
import sys
from pathlib import Path

from . import (art, aseprite, audio, credits, engines, made, manifest, music, packs, palette, pictures, pipeline,
               sfxr, touchup, ui)

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

    check = commands.add_parser("check", help="check finished files: image size, frames, palette; sound format")
    check.add_argument("ids", nargs="*", help="asset ids (default: every image, .wav and .ogg asset whose file exists)")

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

    sfx = commands.add_parser("sfx", help="make sound effects (sfxr) and clean up sound files")
    sfx_commands = sfx.add_subparsers(dest="sfx_command", required=True)
    sfx_new = sfx_commands.add_parser("new", help="start sounds/<id>.yaml from an sfxr preset")
    sfx_new.add_argument("asset", help="asset id in the manifest")
    sfx_new.add_argument("--preset", choices=sfxr.PRESETS, help="sfxr preset")
    sfx_new.add_argument("--seed", type=int, default=1, help="which random variation of the preset")
    sfx_new.add_argument("--from", dest="from_file", help="copy parameters from this .yaml (e.g. a variant)")
    sfx_new.add_argument("--force", action="store_true", help="replace an existing parameter file")
    sfx_make = sfx_commands.add_parser("make", help="render sfxr parameter files to WAV")
    sfx_make.add_argument("ids", nargs="*", help="asset ids (default: every source: sfxr asset with a .yaml)")
    sfx_make.add_argument("--peak", type=float, help="peak level in dBFS (default: audio.sfx_peak_db, else -1)")
    sfx_variants = sfx_commands.add_parser("variants", help="write several versions to listen to and pick from")
    sfx_variants.add_argument("asset")
    sfx_variants.add_argument("--count", type=int, default=5)
    sfx_variants.add_argument("--preset", choices=sfxr.PRESETS,
                              help="fresh seeds of a preset (default: small changes to the current sound)")
    sfx_variants.add_argument("--amount", type=float, default=0.05, help="how much to change (default 0.05)")
    sfx_clean = sfx_commands.add_parser("clean", help="any sound file -> trimmed, normalized mono 16-bit WAV")
    sfx_clean.add_argument("source", help="sound file (wav, mp3, ogg, flac...)")
    sfx_clean.add_argument("asset", help="asset id in the manifest")
    sfx_clean.add_argument("--no-trim", action="store_true", help="keep silence at the start and end")
    sfx_clean.add_argument("--peak", type=float, help="peak level in dBFS (default: audio.sfx_peak_db, else -1)")
    sfx_clean.add_argument("--match", help="match the loudness of this sound file (e.g. the one being "
                           "replaced); the peak level becomes a ceiling")
    sfx_clean.add_argument("--max-seconds", type=float, help="cut to at most this long, with a short fade")
    sfx_clean.add_argument("--force", action="store_true", help="overwrite an existing asset file")
    sfx_info = sfx_commands.add_parser("info", help="describe sounds in numbers (length, level, brightness, shape)")
    sfx_info.add_argument("targets", nargs="+", help="asset ids or sound file paths")

    mus = commands.add_parser("music", help="render the game's music scores or import music as looping OGG")
    music_commands = mus.add_subparsers(dest="music_command", required=True)
    music_render = music_commands.add_parser("render", help="render source: synth tracks with the game's Godot script")
    music_render.add_argument("ids", nargs="*", help="asset ids (default: every source: synth music asset)")
    music_render.add_argument("--loudness", type=float,
                              help="match this loudness in LUFS (default: audio.music_lufs, else as rendered)")
    music_render.add_argument("--keep-wav", help="also keep the rendered WAVs in this folder")
    music_clean = music_commands.add_parser("clean", help="any music file -> OGG (44100 Hz), optional cut and loudness")
    music_clean.add_argument("source", help="music file (wav, mp3, ogg, flac...)")
    music_clean.add_argument("asset", help="asset id in the manifest")
    music_clean.add_argument("--loudness", type=float, help="target LUFS (default: audio.music_lufs, else -16)")
    music_clean.add_argument("--keep-level", action="store_true", help="don't change the loudness")
    music_clean.add_argument("--start", type=float, help="cut: start at this second")
    music_clean.add_argument("--end", type=float, help="cut: end at this second (pick loop points)")
    music_clean.add_argument("--force", action="store_true", help="overwrite an existing asset file")
    music_make = music_commands.add_parser("make", help="make music from a description (music engine) into music-takes/")
    music_make.add_argument("prompt", help="what it should sound like, e.g. \"Instrumental tense dungeon music, low strings\"")
    music_make.add_argument("--seconds", type=int, default=60, help="length (default 60)")
    music_make.add_argument("--takes", type=int, default=1, help="how many (default 1)")
    music_make.add_argument("--bpm", type=int, help="tempo (default: the model chooses)")
    music_make.add_argument("--key", default="", help="e.g. \"D minor\" (default: the model chooses)")
    music_make.add_argument("--lyrics", default="", help="words to sing (default: instrumental)")
    music_make.add_argument("--steps", type=int, default=8, help="detail (default 8)")
    music_make.add_argument("--seed", type=int, help="seed of the first take (default: random)")
    music_make.add_argument("--planner", action="store_true", help="plan the song first (better structure; much slower on AMD)")
    music_use = music_commands.add_parser("use", help="make an AI take a music asset's looping OGG (source: ai)")
    music_use.add_argument("take", help="file name in music-takes/")
    music_use.add_argument("asset", help="music asset id")
    music_use.add_argument("--start", type=float, help="loop start in seconds")
    music_use.add_argument("--end", type=float, help="loop end in seconds")
    music_use.add_argument("--loudness", type=float, help="target LUFS (default: audio.music_lufs, else -16)")
    music_use.add_argument("--force", action="store_true", help="replace an existing asset file")
    music_info = music_commands.add_parser("info", help="length, loudness and how cleanly a track loops")
    music_info.add_argument("targets", nargs="+", help="asset ids or music file paths")

    eng = commands.add_parser("engines", help="local AI models (pictures...): set up, list, remove")
    eng_commands = eng.add_subparsers(dest="engines_command", required=True)
    eng_commands.add_parser("list", help="each engine: set up or not, its model and license")
    eng_setup = eng_commands.add_parser("setup", help="install an engine's Python and PyTorch for this PC's graphics card")
    eng_setup.add_argument("name", choices=list(engines.ENGINES))
    eng_remove = eng_commands.add_parser("remove", help="delete an engine's Python environment (keeps model files)")
    eng_remove.add_argument("name", choices=list(engines.ENGINES))

    pic = commands.add_parser("picture", help="make pictures from a description (picture engine) into pictures/")
    pic.add_argument("prompt", help="what to draw, e.g. \"pixel art sprite of a bat, plain white background\"")
    pic.add_argument("--takes", type=int, default=1, help="how many (default 1)")
    pic.add_argument("--size", default="1024x1024", help="WxH (default 1024x1024)")
    pic.add_argument("--steps", type=int, default=4, help="painting steps (default 4)")
    pic.add_argument("--seed", type=int, help="seed of the first take (default: random)")
    pic.add_argument("--tile", action="store_true", help="repeats without a seam (textures)")
    pic.add_argument("--from", dest="refs", action="append", default=[],
                     help="a picture in pictures/ to work from (repeatable)")
    pic.add_argument("--for", dest="for_asset", default="",
                     help="the asset it's for: names the files after it, and Use as asset picks it")
    pic_cut = commands.add_parser("picture-cutout", help="a copy of a picture with a transparent background (cutout engine)")
    pic_cut.add_argument("pictures", nargs="+", help="file names in pictures/")
    pic_use = commands.add_parser("picture-use", help="make a picture an image asset's file (shrunk, palette)")
    pic_use.add_argument("picture", help="file name in pictures/")
    pic_use.add_argument("asset", help="asset id")
    pic_use.add_argument("--keep-background", action="store_true", help="don't remove the background")
    pic_use.add_argument("--no-palette", action="store_true", help="don't snap colors to the palette")
    pic_use.add_argument("--no-outline", action="store_true", help="no outline, even if the manifest's sprites: sets one")
    pic_use.add_argument("--frame", default="", help="with frame_files: which frame file, e.g. ghoul_walk_1")
    pic_use.add_argument("--force", action="store_true", help="replace an existing asset file")

    pic_frames = commands.add_parser("picture-frames", help="pictures as an animated sprite's frame files, with one shared crop")
    pic_frames.add_argument("asset", help="asset id (frame_files sprite)")
    pic_frames.add_argument("frames", nargs="+", help="<frame>=<picture>, e.g. ghoul_walk_1=ghoul-walk-1-5-cutout.png")
    pic_frames.add_argument("--keep-background", action="store_true", help="don't remove the background")
    pic_frames.add_argument("--no-palette", action="store_true", help="don't snap colors to the palette")
    pic_frames.add_argument("--no-outline", action="store_true", help="no outline, even if the manifest's sprites: sets one")

    touch = commands.add_parser("touchup", help="a sprite as Claude's text rows (art/<id>.yaml), to touch up by hand")
    touch.add_argument("asset", help="asset id")
    touch.add_argument("--from", dest="pictures", nargs="+", default=[],
                       help="<frame>=<picture> (or one picture for a still image); default: the asset's own PNGs")
    touch.add_argument("--keep-background", action="store_true", help="don't remove the background")
    touch.add_argument("--no-palette", action="store_true", help="don't snap colors to the palette")
    touch.add_argument("--no-outline", action="store_true", help="no outline, even if the manifest's sprites: sets one")
    touch.add_argument("--force", action="store_true", help="replace an existing text sprite")

    snd = commands.add_parser("sound", help="make sound effects from a description (sound engine) into sound-takes/")
    snd.add_argument("prompt", help="e.g. \"a heavy wooden door slams shut in a stone hall\"")
    snd.add_argument("--seconds", type=float, default=2.0, help="length (default 2)")
    snd.add_argument("--takes", type=int, default=3, help="how many (default 3)")
    snd.add_argument("--steps", type=int, default=8, help="detail (default 8)")
    snd.add_argument("--seed", type=int, help="seed of the first take (default: random)")
    snd.add_argument("--stereo", action="store_true", help="keep stereo (default mono)")
    snd.add_argument("--loop", action="store_true", help="seamless loop (ambience: fire, wind, rain)")
    voc = commands.add_parser("voice", help="read words aloud in a described voice (voice engine) into voice-takes/")
    voc.add_argument("text", help="the words to say (up to 1,500 characters)")
    voc.add_argument("--who", default="", help="the voice: age, man or woman, sound, accent, pace")
    voc.add_argument("--tone", default="", help="how it's said: whispering, shouting, weary...")
    voc.add_argument("--language", default="English")
    voc.add_argument("--takes", type=int, default=2, help="how many (default 2)")
    voc.add_argument("--seed", type=int, help="seed of the first take (default: random)")
    take_use = commands.add_parser("take-use", help="make a sound or voice take a .wav asset (mono, trimmed; source: ai)")
    take_use.add_argument("kind", choices=["sound", "voice"])
    take_use.add_argument("take", help="file name in sound-takes/ or voice-takes/")
    take_use.add_argument("asset", help="asset id (a .wav asset)")
    take_use.add_argument("--match", help="match the loudness of this sound file (e.g. the one it replaces)")
    take_use.add_argument("--force", action="store_true", help="replace an existing asset file")

    page = commands.add_parser("ui", help="open the asset page in a browser window (this PC only)")
    page.add_argument("--port", type=int, default=ui.DEFAULT_PORT, help=f"port (default: {ui.DEFAULT_PORT})")
    page.add_argument("--no-window", action="store_true", help="don't open a window; just print the address")
    page.add_argument("--launcher", action="store_true",
                      help="write 'Start Gamekit.bat' next to the manifest (double-click to open the page) and exit")

    args = parser.parse_args(argv)
    handlers = {"init": _init, "validate": _validate, "status": _status, "credits": _credits,
                "draw": _draw, "export": _export, "check": _check, "preview": _preview, "pack": _pack,
                "sfx": _sfx, "music": _music, "ui": _ui, "engines": _engines, "picture": _picture,
                "picture-cutout": _picture_cutout, "picture-use": _picture_use,
                "picture-frames": _picture_frames, "touchup": _touchup, "sound": _sound, "voice": _voice,
                "take-use": _take_use}
    try:
        return handlers[args.command](args)
    except (manifest.ManifestError, palette.PaletteError, art.ArtError, aseprite.AsepriteError,
            packs.PackError, audio.AudioError, music.MusicError, ui.UserError, engines.EngineError,
            pictures.PictureError, touchup.TouchUpError) as error:
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
    if args.ids:
        assets = pipeline.image_assets(loaded, args.ids)
    else:
        assets = [a for a in loaded.assets if loaded.asset_path(a).suffix.lower() in (".png", ".wav", ".ogg")
                  and loaded.asset_path(a).exists()]
    problems = [p for a in assets for p in pipeline.check(loaded, a, colors)]
    for problem in problems:
        print(f"- {problem}")
    print(f"checked {len(assets)} file{'s' if len(assets) != 1 else ''}: "
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

    if out_suffix == ".wav":
        if source.suffix.lower() not in packs.AUDIO_TYPES:
            raise packs.PackError(f"{source.name} is not a sound file")
        problems = pipeline.clean_into(loaded, asset, source)
        print(f"{asset.id}: {pack.name}/{args.file} -> {asset.file} (trimmed, normalized, mono 16-bit)")
        for problem in problems:
            print(f"  - {problem}")
    elif out_suffix == ".ogg":
        if source.suffix.lower() not in packs.AUDIO_TYPES:
            raise packs.PackError(f"{source.name} is not a sound file")
        lufs = loaded.music_lufs if loaded.music_lufs is not None else -16.0
        note = music.encode_ogg(source, out, loudness=lufs)
        print(f"{asset.id}: {pack.name}/{args.file} -> {asset.file} (OGG, {lufs:g} LUFS)")
        if note:
            print(f"  {note}")
        for problem in pipeline.check_ogg(loaded, asset):
            print(f"  - {problem}")
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
        pipeline.save_image(loaded, asset, image, sidecar)
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


def _sfx(args: argparse.Namespace) -> int:
    loaded = manifest.load(args.manifest)
    return {"new": _sfx_new, "make": _sfx_make, "variants": _sfx_variants,
            "clean": _sfx_clean, "info": _sfx_info}[args.sfx_command](args, loaded)


def _asset(loaded: manifest.Manifest, asset_id: str) -> manifest.Asset:
    for a in loaded.assets:
        if a.id == asset_id:
            return a
    raise audio.AudioError(f"{asset_id!r} is not in the manifest")


def _sfx_new(args: argparse.Namespace, loaded: manifest.Manifest) -> int:
    asset = _asset(loaded, args.asset)
    src = pipeline.sfx_source(loaded, asset)
    if src.exists() and not args.force:
        raise audio.AudioError(f"{src} already exists; add --force to replace it")
    if args.from_file:
        try:
            params, name = sfxr.load(Path(args.from_file)), ""
        except (OSError, ValueError) as error:
            raise audio.AudioError(str(error)) from None
    elif args.preset:
        params, name = sfxr.preset(args.preset, args.seed), args.preset
    else:
        raise audio.AudioError("give --preset <name> or --from <file.yaml>")
    sfxr.save(src, params, name)
    problems = pipeline.make_sfx(loaded, asset)
    print(f"{asset.id}: wrote {src.relative_to(loaded.root).as_posix()} and {asset.file}")
    _print_info(asset.id, loaded.asset_path(asset))
    for problem in problems:
        print(f"  - {problem}")
    return 0


def _sfx_make(args: argparse.Namespace, loaded: manifest.Manifest) -> int:
    if args.ids:
        assets = [_asset(loaded, i) for i in args.ids]
    else:
        assets = [a for a in loaded.assets if a.source == "sfxr"
                  and (src := loaded.source_path(a)) is not None and src.exists()]
    results = [(a, pipeline.make_sfx(loaded, a, args.peak)) for a in assets]
    return _report(results, "rendered")


def _sfx_variants(args: argparse.Namespace, loaded: manifest.Manifest) -> int:
    asset = _asset(loaded, args.asset)
    src = pipeline.sfx_source(loaded, asset)
    if not args.preset and not src.exists():
        raise audio.AudioError(f"{src} not found: give --preset, or start one with `sfx new`")
    base = sfxr.load(src) if not args.preset else None
    folder = src.parent / "variants"
    for n in range(1, max(1, args.count) + 1):
        if args.preset:
            params = sfxr.preset(args.preset, n)
        else:
            params = sfxr.mutate(base, seed=base.seed * 1000 + n, amount=args.amount)
        stem = folder / f"{asset.id}_{n}"
        sfxr.save(stem.with_suffix(".yaml"), params, args.preset or "")
        audio.write_wav(stem.with_suffix(".wav"), audio.clean(sfxr.render(params), peak_db=loaded.sfx_peak_db))
        _print_info(stem.name, stem.with_suffix(".wav"))
    rel = folder.relative_to(loaded.root).as_posix()
    print(f"listen to {rel}/{asset.id}_*.wav; keep one with:")
    print(f"  gamekit sfx new {asset.id} --from {rel}/{asset.id}_<n>.yaml --force")
    return 0


def _sfx_clean(args: argparse.Namespace, loaded: manifest.Manifest) -> int:
    asset = _asset(loaded, args.asset)
    out = loaded.asset_path(asset)
    if out.exists() and not args.force:
        raise audio.AudioError(f"{out} already exists; add --force to replace it")
    problems = pipeline.clean_into(loaded, asset, Path(args.source), not args.no_trim, args.peak,
                                   match=args.match, max_seconds=args.max_seconds)
    print(f"{asset.id}: {args.source} -> {asset.file}")
    _print_info(asset.id, out)
    for problem in problems:
        print(f"  - {problem}")
    if asset.source in manifest.LICENSED_SOURCES and not asset.license:
        print(f"  remember: record where it came from and its license for {asset.id} in the manifest")
    return 0


def _sfx_info(args: argparse.Namespace, loaded: manifest.Manifest) -> int:
    by_id = {a.id: a for a in loaded.assets}
    for target in args.targets:
        path = loaded.asset_path(by_id[target]) if target in by_id else Path(target)
        _print_info(target, path)
    return 0


def _print_info(name: str, path: Path) -> None:
    info = audio.describe(audio.read(path))
    print(f"  {name}: {info.seconds:.2f} s, peak {info.peak_db:.1f} dB, loudness (RMS) {info.rms_db:.1f} dB, "
          f"attack {info.attack_ms:.0f} ms, brightness {info.brightness:.0f}/s")
    print(f"  shape |{audio.envelope_bar(info.envelope)}|")


def _music(args: argparse.Namespace) -> int:
    loaded = manifest.load(args.manifest)
    return {"render": _music_render, "clean": _music_clean, "info": _music_info, "make": _music_make,
            "use": _music_use}[args.music_command](args, loaded)


def _music_make(args: argparse.Namespace, loaded: manifest.Manifest) -> int:
    request = {"prompt": args.prompt, "seconds": args.seconds, "bpm": args.bpm, "key": args.key,
               "lyrics": args.lyrics, "instrumental": not args.lyrics.strip(), "steps": args.steps,
               "planner": args.planner}
    worker = engines.worker("music")
    try:
        for take in range(max(1, args.takes)):
            seed = args.seed + take if args.seed is not None else random.randrange(1, 2**31 - 1)
            out = made.new_path(loaded, "music", args.prompt, seed)
            answer = worker.ask(request | {"out": str(out), "seed": seed}, lambda s: print(f"  {s}", flush=True))
            made.record(out, request | {"seed": answer.get("seed", seed), "model": "ACE-Step 1.5 turbo"})
            print(f"wrote {out.relative_to(loaded.root).as_posix()} (seed {answer.get('seed', seed)})", flush=True)
    finally:
        worker.stop()
    return 0


def _music_use(args: argparse.Namespace, loaded: manifest.Manifest) -> int:
    asset = _asset(loaded, args.asset)
    out = loaded.asset_path(asset)
    if asset.kind != "music" or out.suffix.lower() != ".ogg":
        raise music.MusicError(f"{asset.id} isn't a music asset with an .ogg file")
    if out.exists() and not args.force:
        raise music.MusicError(f"{out} already exists; add --force to replace it")
    lufs = args.loudness if args.loudness is not None else (loaded.music_lufs if loaded.music_lufs is not None else -16.0)
    note = music.encode_ogg(made.path_of(loaded, "music", args.take), out, lufs, start=args.start, end=args.end)
    manifest.set_fields(loaded.path, asset.id, {"source": "ai"} | ({"status": "draft"} if asset.status == "todo" else {}))
    print(f"{asset.id}: {args.take} -> {asset.file} (source: ai)")
    if note:
        print(f"  {note}")
    _print_music(asset.id, out)
    for problem in pipeline.check_ogg(loaded, asset):
        print(f"  - {problem}")
    return 0


def _music_render(args: argparse.Namespace, loaded: manifest.Manifest) -> int:
    assets = pipeline.music_assets(loaded, args.ids)
    if not assets:
        print("nothing to do (no source: synth music in the manifest)")
        return 0
    godot = music.find_godot()
    print(f"rendering {len(assets)} track{'s' if len(assets) != 1 else ''} with {godot}")
    keep = Path(args.keep_wav) if args.keep_wav else None
    results = pipeline.render_music(loaded, assets, godot, args.loudness, keep)
    for asset, _, note in results:
        _print_music(asset.id, loaded.asset_path(asset))
        if note:
            print(f"    {note}")
    return _report([(asset, problems) for asset, problems, _ in results], "rendered")


def _music_clean(args: argparse.Namespace, loaded: manifest.Manifest) -> int:
    asset = _asset(loaded, args.asset)
    out = loaded.asset_path(asset)
    if out.suffix.lower() != ".ogg":
        raise music.MusicError(f"{asset.id}: music files are .ogg, but file is {asset.file}")
    if out.exists() and not args.force:
        raise music.MusicError(f"{out} already exists; add --force to replace it")
    lufs = args.loudness if args.loudness is not None else (
        loaded.music_lufs if loaded.music_lufs is not None else -16.0)
    note = music.encode_ogg(Path(args.source), out, None if args.keep_level else lufs,
                            start=args.start, end=args.end)
    print(f"{asset.id}: {args.source} -> {asset.file}")
    if note:
        print(f"  {note}")
    _print_music(asset.id, out)
    for problem in pipeline.check_ogg(loaded, asset):
        print(f"  - {problem}")
    if asset.source in manifest.LICENSED_SOURCES and not asset.license:
        print(f"  remember: record where it came from and its license for {asset.id} in the manifest")
    return 0


def _music_info(args: argparse.Namespace, loaded: manifest.Manifest) -> int:
    by_id = {a.id: a for a in loaded.assets}
    for target in args.targets:
        _print_music(target, loaded.asset_path(by_id[target]) if target in by_id else Path(target))
    return 0


def _print_music(name: str, path: Path) -> None:
    info = music.describe(path)
    lufs = f"{info.lufs:.1f} LUFS" if info.lufs is not None else "loudness unknown (ffmpeg?)"
    peak = f", true peak {info.true_peak:+.1f} dBTP" if info.true_peak is not None else ""
    print(f"  {name}: {info.seconds:.1f} s, {lufs}{peak}")
    if not info.exact:
        print("    loop point: can't be measured exactly for this file (decoder length differs)")
        return
    print(f"    loop point: jump {info.seam_jump:.3f} (normal movement {info.edge_motion:.3f}), "
          f"silence {info.silent_tail:.2f} s at the end + {info.silent_head:.2f} s at the start")


def _ui(args: argparse.Namespace) -> int:
    path = Path(args.manifest)
    if args.launcher:
        bat = ui.write_launcher(path, Path(__file__).resolve().parent.parent / "gamekit.py")
        print(f"wrote {bat} (double-click it to open the asset page)")
        return 0
    ui.serve(path, args.port, window=not args.no_window)
    return 0


def _engines(args: argparse.Namespace) -> int:
    if args.engines_command == "list":
        print(f"engines folder: {engines.home()}")
        for engine in engines.ENGINES.values():
            info = engines.status(engine)
            state = f"set up (PyTorch {info['torch']})" if info["installed"] else "not set up"
            model = "model downloaded" if info["model_ready"] else "model downloads on first use"
            print(f"- {engine.name}: {state}; {model}\n    {engine.model}, {engine.license}")
        return 0
    if args.engines_command == "setup":
        for line in engines.setup(args.name):
            print(line, flush=True)
        return 0
    folder = engines.remove(args.name)
    print(f"removed {folder} (model files in {engines.models_dir()} are kept)")
    return 0


def _picture(args: argparse.Namespace) -> int:
    loaded = manifest.load(args.manifest)
    size = _size(args.size, "--size")
    assert size is not None
    request = {"prompt": args.prompt, "width": size[0], "height": size[1], "steps": args.steps, "tile": args.tile,
               "refs": [str(pictures.path_of(loaded, name)) for name in args.refs], "for": args.for_asset}
    if args.for_asset:
        _asset(loaded, args.for_asset)
    worker = engines.worker("picture")
    try:
        for take in range(max(1, args.takes)):
            seed = args.seed + take if args.seed is not None else random.randrange(1, 2**31 - 1)
            out = pictures.new_path(loaded, args.for_asset or args.prompt, seed)
            answer = worker.ask(request | {"out": str(out), "seed": seed}, lambda s: print(f"  {s}", flush=True))
            pictures.record(out, request, answer)
            print(f"wrote {out.relative_to(loaded.root).as_posix()} (seed {seed})", flush=True)
    finally:
        worker.stop()
    return 0


def _picture_cutout(args: argparse.Namespace) -> int:
    loaded = manifest.load(args.manifest)
    sources = [pictures.path_of(loaded, name) for name in args.pictures]
    worker = engines.worker("cutout")
    try:
        for source in sources:
            out = pictures.cutout_path(loaded, source.name)
            worker.ask({"in": str(source), "out": str(out)}, lambda s: print(f"  {s}", flush=True))
            pictures.record_cutout(out, source.name, pictures.read_meta(source))
            print(f"wrote {out.relative_to(loaded.root).as_posix()}", flush=True)
    finally:
        worker.stop()
    return 0


def _picture_frames(args: argparse.Namespace) -> int:
    loaded = manifest.load(args.manifest)
    asset = _asset(loaded, args.asset)
    chosen = {}
    for item in args.frames:
        frame, _, name = item.partition("=")
        if not name:
            raise pictures.PictureError(f"{item!r}: write <frame>=<picture>, e.g. {asset.id}_walk_1=walk.png")
        chosen[frame] = name
    problems = pictures.use_frames(loaded, asset, chosen, background=not args.keep_background,
                                   snap=not args.no_palette, outline=not args.no_outline)
    manifest.set_fields(loaded.path, asset.id, {"source": "ai"} | ({"status": "draft"} if asset.status == "todo" else {}))
    print(f"{asset.id}: wrote {', '.join(chosen)} (one shared crop; source: ai)")
    for problem in problems:
        print(f"  - {problem}")
    return 0


def _touchup(args: argparse.Namespace) -> int:
    loaded = manifest.load(args.manifest)
    asset = _asset(loaded, args.asset)
    try:
        if args.pictures:
            chosen = {}
            for item in args.pictures:
                frame, _, name = item.partition("=")
                chosen[frame if name else asset.id] = name or frame
            if not loaded.frame_paths(asset):
                chosen = {asset.id: next(iter(chosen.values()))}
            path, problems = touchup.from_pictures(loaded, asset, chosen, not args.keep_background,
                                                   not args.no_palette, not args.no_outline, args.force)
        else:
            path, problems = touchup.from_files(loaded, asset, args.force)
    except touchup.TouchUpError as error:
        if str(error).startswith("REPLACE:"):
            raise touchup.TouchUpError(f"{str(error)[8:]} already exists; add --force to replace it") from None
        raise
    print(f"{asset.id}: wrote {path.relative_to(loaded.root).as_posix()} (source: claude) and rendered it")
    for problem in problems:
        print(f"  - {problem}")
    return 0


def _picture_use(args: argparse.Namespace) -> int:
    loaded = manifest.load(args.manifest)
    asset = _asset(loaded, args.asset)
    target = {path.stem: path for _, _, path in loaded.frame_paths(asset)}.get(args.frame, loaded.asset_path(asset))
    if target.exists() and not args.force:
        raise pictures.PictureError(f"{target} already exists; add --force to replace it")
    problems = pictures.use_as_asset(loaded, asset, args.picture, background=not args.keep_background,
                                     snap=not args.no_palette, outline=not args.no_outline, frame=args.frame)
    manifest.set_fields(loaded.path, asset.id, {"source": "ai"} | ({"status": "draft"} if asset.status == "todo" else {}))
    print(f"{args.frame or asset.id}: {args.picture} -> {target.relative_to(loaded.root).as_posix()} (source: ai)")
    for problem in problems:
        print(f"  - {problem}")
    return 0


def _ai_takes(loaded: manifest.Manifest, kind: str, request: dict, takes: int, seed: int | None, describe: str) -> int:
    worker = engines.worker(kind)
    try:
        for take in range(max(1, takes)):
            used = seed + take if seed is not None else random.randrange(1, 2**31 - 1)
            out = made.new_path(loaded, kind, describe, used)
            answer = worker.ask(request | {"out": str(out), "seed": used}, lambda s: print(f"  {s}", flush=True))
            made.record(out, request | {"seed": answer.get("seed", used), "seconds": answer.get("seconds")})
            print(f"wrote {out.relative_to(loaded.root).as_posix()} ({answer.get('seconds')} s, seed {used})", flush=True)
    finally:
        worker.stop()
    return 0


def _sound(args: argparse.Namespace) -> int:
    loaded = manifest.load(args.manifest)
    request = {"prompt": args.prompt, "seconds": max(0.5, min(30.0, args.seconds)), "steps": args.steps,
               "mono": not args.stereo, "loop": args.loop, "model": "Stable Audio 3 Small SFX"}
    return _ai_takes(loaded, "sound", request, args.takes, args.seed, args.prompt)


def _voice(args: argparse.Namespace) -> int:
    loaded = manifest.load(args.manifest)
    if len(args.text) > 1500:
        raise engines.EngineError("up to 1,500 characters a reading; split longer text")
    request = {"text": args.text, "who": args.who, "tone": args.tone, "language": args.language,
               "model": "Qwen3-TTS 1.7B VoiceDesign"}
    return _ai_takes(loaded, "voice", request, args.takes, args.seed, args.text)


def _take_use(args: argparse.Namespace) -> int:
    loaded = manifest.load(args.manifest)
    asset = _asset(loaded, args.asset)
    out = loaded.asset_path(asset)
    if out.suffix.lower() != ".wav":
        raise audio.AudioError(f"{asset.id}'s file is {asset.file}; sounds and voices become .wav assets")
    if out.exists() and not args.force:
        raise audio.AudioError(f"{out} already exists; add --force to replace it")
    source = made.path_of(loaded, args.kind, args.take)
    problems = pipeline.clean_into(loaded, asset, source, do_trim=not made.read_meta(source).get("loop"),
                                   match=args.match)
    manifest.set_fields(loaded.path, asset.id, {"source": "ai"} | ({"status": "draft"} if asset.status == "todo" else {}))
    print(f"{asset.id}: {args.take} -> {asset.file} (source: ai)")
    _print_info(asset.id, out)
    for problem in problems:
        print(f"  - {problem}")
    return 0
