import contextlib
import io
import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "gamekit" / "scripts"))

from PIL import Image  # noqa: E402

from gamekit_lib import art, aseprite, cli, manifest, pipeline  # noqa: E402
from gamekit_lib.palette import Entry  # noqa: E402

ENTRIES = [Entry((0, 0, 0), "k"), Entry((255, 255, 255), "w"), Entry((200, 30, 30), "red")]


class TextSpriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def sprite(self, text: str) -> art.TextSprite:
        path = self.folder / "s.yaml"
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        return art.load_text_sprite(path, ENTRIES)

    def test_still_uses_palette_names_as_keys(self) -> None:
        image, sidecar = art.render(self.sprite("""
            rows: |
              .k.
              kwk
            """))
        self.assertIsNone(sidecar)
        self.assertEqual(image.size, (3, 2))
        self.assertEqual(image.getpixel((0, 0)), (0, 0, 0, 0))
        self.assertEqual(image.getpixel((1, 0)), (0, 0, 0, 255))
        self.assertEqual(image.getpixel((1, 1)), (255, 255, 255, 255))

    def test_keys_by_name_index_and_hex(self) -> None:
        image, _ = art.render(self.sprite("""
            keys: {a: red, b: 1, c: "#0000ff"}
            rows: |
              abc
            """))
        self.assertEqual([image.getpixel((x, 0))[:3] for x in range(3)],
                         [(200, 30, 30), (255, 255, 255), (0, 0, 255)])

    def test_animation_sheet_and_sidecar(self) -> None:
        image, sidecar = art.render(self.sprite("""
            frames:
              idle:
                - |
                  kk
                  kk
              walk:
                - |
                  k.
                  .k
                - |
                  .k
                  k.
                - |
                  ww
                  ww
            """))
        self.assertEqual(image.size, (6, 4))  # 3 columns (longest animation) x 2 rows
        self.assertEqual(sidecar, {"frame_size": [2, 2],
                                   "animations": {"idle": [[0, 0]], "walk": [[0, 2], [2, 2], [4, 2]]}})
        self.assertEqual(image.getpixel((4, 2)), (255, 255, 255, 255))

    def test_errors(self) -> None:
        with self.assertRaisesRegex(art.ArtError, "different lengths"):
            self.sprite("rows: |\n  kk\n  k\n")
        with self.assertRaisesRegex(art.ArtError, r"unknown key 'z' at row 1, column 2"):
            art.render(self.sprite("rows: |\n  kz\n"))
        with self.assertRaisesRegex(art.ArtError, "same size"):
            art.render(self.sprite("frames:\n  a:\n    - |\n      kk\n    - |\n      k\n"))
        with self.assertRaisesRegex(art.ArtError, "out of range"):
            self.sprite("keys: {a: 9}\nrows: |\n  a\n")

    def test_off_palette_ignores_transparent(self) -> None:
        image = Image.new("RGBA", (3, 1), (0, 0, 0, 0))
        image.putpixel((0, 0), (0, 0, 0, 255))
        image.putpixel((1, 0), (1, 2, 3, 255))
        image.putpixel((2, 0), (255, 255, 255, 128))
        off, partial = art.off_palette(image, [e.color for e in ENTRIES])
        self.assertEqual(off, {"010203": 1})
        self.assertEqual(partial, 1)


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        (self.folder / "palette.hex").write_text("000000 k\nffffff w\n", encoding="utf-8")
        (self.folder / "art").mkdir()
        self._cwd = os.getcwd()
        os.chdir(self.folder)

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def write_manifest(self, assets: str) -> manifest.Manifest:
        (self.folder / "assets.yaml").write_text(
            "game: T\noutput: assets\npalette: palette.hex\nassets:\n" + assets, encoding="utf-8")
        return manifest.load(self.folder / "assets.yaml")

    def run_cli(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = cli.main(list(args))
        return code, out.getvalue()

    def test_draw_check_preview(self) -> None:
        self.write_manifest(
            "  - {id: hero, kind: sprite, source: claude, file: sprites/hero.png, size: [2, 2], frames: {walk: 2}}\n")
        (self.folder / "art" / "hero.yaml").write_text(
            "frames:\n  walk:\n    - |\n      kw\n      wk\n    - |\n      wk\n      kw\n", encoding="utf-8")
        code, out = self.run_cli("draw", "--all")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.folder / "assets" / "sprites" / "hero.png").exists())
        side = json.loads((self.folder / "assets" / "sprites" / "hero.json").read_text(encoding="utf-8"))
        self.assertEqual(side["image"], "hero.png")
        self.assertEqual(self.run_cli("check")[0], 0)
        code, out = self.run_cli("preview", "--scale", "8")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.folder / "preview.png").exists())

    def test_check_reports_size_frames_and_palette(self) -> None:
        loaded = self.write_manifest(
            "  - {id: icon, kind: icon, source: pack, file: icon.png, size: [4, 4]}\n"
            "  - {id: hero, kind: sprite, source: self, file: hero.png, size: [2, 2], frames: {walk: 3}}\n"
            "  - {id: tiles, kind: tileset, source: self, file: tiles.png, size: [2, 2]}\n")
        (self.folder / "assets").mkdir()
        Image.new("RGBA", (3, 3), (9, 9, 9, 255)).save(self.folder / "assets" / "icon.png")
        Image.new("RGBA", (4, 2), (0, 0, 0, 255)).save(self.folder / "assets" / "hero.png")
        (self.folder / "assets" / "hero.json").write_text(json.dumps(
            {"frame_size": [2, 2], "animations": {"walk": [[0, 0], [2, 0]]}}), encoding="utf-8")
        Image.new("RGBA", (4, 6), (0, 0, 0, 255)).save(self.folder / "assets" / "tiles.png")
        colors = [(0, 0, 0), (255, 255, 255)]
        icon, hero, tiles = loaded.assets
        icon_problems = pipeline.check(loaded, icon, colors)
        self.assertTrue(any("3x3, manifest says 4x4" in p for p in icon_problems))
        self.assertTrue(any("off-palette" in p and "090909" in p for p in icon_problems))
        self.assertTrue(any("don't match manifest frames" in p for p in pipeline.check(loaded, hero, colors)))
        self.assertEqual(pipeline.check(loaded, tiles, colors), [])

    def test_draw_fails_cleanly_without_source(self) -> None:
        self.write_manifest("  - {id: hero, kind: sprite, source: claude, file: hero.png, size: [2, 2]}\n")
        code, out = self.run_cli("draw", "hero")
        self.assertEqual(code, 1)
        self.assertIn("art/hero.yaml not found", out.replace("\\", "/"))


class AsepriteTests(unittest.TestCase):
    def test_sidecar_from_tags(self) -> None:
        raw = {"frames": [
            {"filename": "idle#0", "frame": {"x": 0, "y": 0, "w": 16, "h": 16}},
            {"filename": "idle#1", "frame": {"x": 16, "y": 0, "w": 16, "h": 16}},
            {"filename": "walk#0", "frame": {"x": 0, "y": 16, "w": 16, "h": 16}},
        ]}
        self.assertEqual(aseprite.sidecar_from_aseprite(raw), {
            "frame_size": [16, 16], "animations": {"idle": [[0, 0], [16, 0]], "walk": [[0, 16]]}})

    def test_untagged_single_frame_is_still(self) -> None:
        raw = {"frames": [{"filename": "#0", "frame": {"x": 0, "y": 0, "w": 8, "h": 8}}]}
        self.assertIsNone(aseprite.sidecar_from_aseprite(raw))

    def test_command_uses_rows_and_split_tags(self) -> None:
        command = aseprite.export_command("ase", Path("a.aseprite"), Path("a.png"), Path("a.json"))
        for flag in ("--batch", "--sheet", "--data", "--split-tags", "json-array"):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("--sheet-type") + 1], "rows")

    @unittest.skipIf(os.name == "nt", "fake Aseprite is a shell script")
    def test_export_with_fake_aseprite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            fake = folder / "aseprite"
            # Writes a 4x2 sheet and a two-frame "walk" tag, like the real CLI would.
            fake.write_text(textwrap.dedent(f"""\
                #!{sys.executable}
                import json, sys
                from PIL import Image
                args = sys.argv
                Image.new("RGBA", (4, 2), (0, 0, 0, 255)).save(args[args.index("--sheet") + 1])
                frames = [{{"filename": "walk#0", "frame": {{"x": 0, "y": 0, "w": 2, "h": 2}}}},
                          {{"filename": "walk#1", "frame": {{"x": 2, "y": 0, "w": 2, "h": 2}}}}]
                open(args[args.index("--data") + 1], "w").write(json.dumps({{"frames": frames}}))
                """), encoding="utf-8")
            fake.chmod(0o755)
            (folder / "hero.aseprite").write_bytes(b"")
            sidecar = aseprite.export(folder / "hero.aseprite", folder / "out" / "hero.png", str(fake))
            self.assertEqual(sidecar["animations"], {"walk": [[0, 0], [2, 0]]})
            self.assertTrue((folder / "out" / "hero.png").exists())

    def test_missing_configured_path_errors(self) -> None:
        old = os.environ.get("GAMEKIT_ASEPRITE")
        os.environ["GAMEKIT_ASEPRITE"] = "/nope/aseprite"
        try:
            with self.assertRaisesRegex(aseprite.AsepriteError, "doesn't exist"):
                aseprite.find()
        finally:
            if old is None:
                del os.environ["GAMEKIT_ASEPRITE"]
            else:
                os.environ["GAMEKIT_ASEPRITE"] = old


if __name__ == "__main__":
    unittest.main()
