import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "gamekit" / "scripts"))

from PIL import Image  # noqa: E402

from gamekit_lib import cli, codeart, manifest, pipeline  # noqa: E402

SCRIPT = """class_name PixelArt
## Sprites as text. "P"/"p" are the player colors.
const PALETTE: Dictionary[String, Color] = {
	".": Color(0, 0, 0, 0),
	"k": Color(0.0, 0.0, 0.0),
	"w": Color(1.0, 1.0, 1.0),
	"h": Color(1, 0, 0, 0.5),  # half see-through red
}

const SPRITES: Dictionary[String, Array] = {
	# --- a comment between sprites ---
	"blob": [
		"kk",
		"wP",
	],
	"blob_walk_1": [
		"k.",
		"pw",
	],
	"blob_walk_2": [".k", "wp"],
	"tall": [
		"k",
		"k",
		"h",
	],
	"oops": ["kz"],
}

const OTHER := {"x": 1}
"""

MANIFEST = """game: T
code_art: src/pixel_art.gd
assets:
  - {id: blob, kind: sprite, source: claude, file: art/blob.png, size: [2, 2], frames: {idle: 1, walk: 2}}
  - {id: hero, kind: sprite, source: claude, file: art/hero.png, size: [1, 3], replaces: tall}
  - {id: oops, kind: icon, source: claude, file: art/oops.png, size: [2, 1]}
  - {id: ghost, kind: icon, source: claude, file: art/ghost.png, size: [2, 2]}
"""


class CodeArtTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "src").mkdir()
        (self.root / "src" / "pixel_art.gd").write_text(SCRIPT, encoding="utf-8")
        (self.root / "assets.yaml").write_text(MANIFEST, encoding="utf-8")
        self.m = manifest.load(self.root / "assets.yaml")
        self.by_id = {a.id: a for a in self.m.assets}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_parse(self) -> None:
        palette, sprites = codeart.parse(SCRIPT)
        self.assertEqual(palette["w"], (255, 255, 255, 255))
        self.assertEqual(palette["h"], (255, 0, 0, 128))
        self.assertEqual(sprites["blob_walk_2"], [".k", "wp"])
        self.assertEqual(set(sprites), {"blob", "blob_walk_1", "blob_walk_2", "tall", "oops"})

    def test_animation_sheet_and_player_colors(self) -> None:
        image = codeart.render(self.m, self.by_id["blob"])
        self.assertEqual(image.size, (4, 4))  # idle row (1 frame), walk row (2 frames)
        self.assertEqual(image.getpixel((1, 1)), (255, 0, 255, 255))  # P
        self.assertEqual(image.getpixel((0, 3)), (128, 0, 128, 255))  # walk_1's p
        self.assertEqual(image.getpixel((2, 2))[3], 0)  # "." is transparent

    def test_replaces_names_the_sprite(self) -> None:
        image = codeart.render(self.m, self.by_id["hero"])
        self.assertEqual(image.size, (1, 3))
        self.assertTrue(codeart.has_art(self.m, self.by_id["hero"]))
        self.assertFalse(codeart.has_art(self.m, self.by_id["ghost"]))
        self.assertIsNone(codeart.render(self.m, self.by_id["ghost"]))

    def test_unknown_character(self) -> None:
        with self.assertRaisesRegex(codeart.CodeArtError, "'z'"):
            codeart.render(self.m, self.by_id["oops"])

    def test_reloads_when_the_script_changes(self) -> None:
        codeart.render(self.m, self.by_id["blob"])
        path = self.root / "src" / "pixel_art.gd"
        path.write_text(SCRIPT.replace('"tall": [', '"ghost": ["kk", "kk"],\n\t"tall": ['), encoding="utf-8")
        import os
        os.utime(path, (1, 1))  # a different modified time, even on fast file systems
        self.assertEqual(codeart.render(self.m, self.by_id["ghost"]).size, (2, 2))

    def test_validate_reports_a_missing_script(self) -> None:
        self.assertEqual(manifest.validate(self.m, check_files=False), [])
        self.m.code_art = "src/nope.gd"
        self.assertIn("code_art: src/nope.gd not found", manifest.validate(self.m, check_files=False))
        self.assertFalse(codeart.has_art(self.m, self.by_id["blob"]))

    def test_no_code_art(self) -> None:
        self.m.code_art = ""
        self.assertIsNone(codeart.render(self.m, self.by_id["blob"]))

    def test_a_file_is_used_before_code_art(self) -> None:
        (self.root / "assets" / "art").mkdir(parents=True)
        Image.new("RGBA", (2, 2), (0, 255, 0, 255)).save(self.root / "assets" / "art" / "ghost.png")
        items = pipeline.preview_items(self.m, [self.by_id["ghost"]])
        self.assertEqual(items[0][1].getpixel((0, 0)), (0, 255, 0, 255))


class SeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "src").mkdir()
        (self.root / "src" / "pixel_art.gd").write_text(SCRIPT, encoding="utf-8")
        # k matches the code's color, w is a different white, so w needs a `keys:` line
        (self.root / "palette.hex").write_text("000000 k\nf0f0f0 w\nff00ff P\n800080 p\n", encoding="utf-8")
        (self.root / "assets.yaml").write_text(MANIFEST.replace("code_art:", "palette: palette.hex\ncode_art:") +
                                               "  - {id: blob2, kind: sprite, source: claude, file: art/blob2.png,"
                                               " size: [2, 2], frames: {idle: 1, walk: 3}, replaces: blob}\n",
                                               encoding="utf-8")
        self.m = manifest.load(self.root / "assets.yaml")
        self.by_id = {a.id: a for a in self.m.assets}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_cli(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = cli.main(["-m", str(self.root / "assets.yaml"), *args])
        return code, out.getvalue()

    def test_seeded_sprite_draws_like_the_code(self) -> None:
        text, warnings = codeart.seed_text(self.m, self.by_id["blob"], pipeline.palette_entries(self.m))
        self.assertEqual(warnings, [])
        self.assertIn('"w": \'ffffff\'', text)
        self.assertIn('"k": \'k\'', text)  # same color as the palette's k
        (self.root / "art").mkdir()
        (self.root / "art" / "blob.yaml").write_text(text, encoding="utf-8")
        draft = pipeline.draft_image(self.m, self.by_id["blob"])
        self.assertEqual(list(draft.getdata()), list(codeart.render(self.m, self.by_id["blob"]).getdata()))
        self.assertFalse((self.root / "assets").exists())  # nothing written into the game

    def test_black_stays_a_color(self) -> None:
        (self.root / "palette.hex").write_text("111111 k\nf0f0f0 w\n", encoding="utf-8")
        text, _ = codeart.seed_text(self.m, self.by_id["hero"], pipeline.palette_entries(self.m))
        self.assertIn("\"k\": '000000'", text)  # unquoted, YAML would read 000000 as palette index 0
        (self.root / "art").mkdir()
        (self.root / "art" / "hero.yaml").write_text(text, encoding="utf-8")
        self.assertEqual(pipeline.draft_image(self.m, self.by_id["hero"]).getpixel((0, 0)), (0, 0, 0, 255))

    def test_missing_frames_copy_the_one_before(self) -> None:
        text, warnings = codeart.seed_text(self.m, self.by_id["blob2"], [])
        self.assertEqual(warnings, ["blob2: the code has no blob_walk_3; it starts as a copy of the frame before"])
        self.assertEqual(text.count("- |"), 4)

    def test_still_image_and_see_through_colors(self) -> None:
        text, warnings = codeart.seed_text(self.m, self.by_id["hero"], [])
        self.assertIn("rows: |\n  k\n  k\n  h\n", text)
        self.assertEqual(warnings, ["hero: 'h' is see-through in the code; text sprites draw it solid"])

    def test_cli_seed_never_overwrites(self) -> None:
        (self.root / "art").mkdir()
        (self.root / "art" / "hero.yaml").write_text("rows: |\n  k\n", encoding="utf-8")
        code, out = self.run_cli("seed", "--kind", "sprite")
        self.assertEqual(code, 0)
        self.assertIn("seeded 2 text sprites", out)  # blob, blob2; hero already has one
        self.assertEqual((self.root / "art" / "hero.yaml").read_text(encoding="utf-8"), "rows: |\n  k\n")
        code, out = self.run_cli("seed", "hero", "ghost")
        self.assertIn("hero: skipped (art/hero.yaml already exists)", out)
        self.assertIn("ghost: skipped (no 'ghost' in src/pixel_art.gd)", out)

    def test_cli_preview_compare(self) -> None:
        self.assertEqual(self.run_cli("seed", "blob")[0], 0)
        out_png = self.root / "compare.png"
        code, out = self.run_cli("preview", "--compare", "-o", str(out_png))
        self.assertEqual(code, 0, out)
        self.assertIn("(2 images)", out)  # blob now (code art) + blob draft; assets without a draft left out
        self.assertTrue(out_png.exists())
        code, out = self.run_cli("preview", "--kind", "sprite", "--status", "todo", "-o", str(out_png))
        self.assertIn("(3 images)", out)  # code art of blob, hero, blob2
        code, out = self.run_cli("preview", "--kind", "icon", "-o", str(out_png))
        self.assertEqual(code, 1)  # ghost has no file or code art; oops' code art is broken
        self.assertIn("nothing to preview", out)
        code, out = self.run_cli("preview", "--bg", "nope", "-o", str(out_png))
        self.assertEqual(code, 1)


class FrameNameTests(unittest.TestCase):
    def test_names(self) -> None:
        a = manifest.Asset(id="cultist", kind="sprite", source="claude", frames={"idle": 2, "walk": 2, "attack": 1})
        self.assertEqual([n for _, _, n in manifest.frame_names(a, "cultist")],
                         ["cultist", "cultist_1", "cultist_walk_1", "cultist_walk_2", "cultist_attack"])
        still = manifest.Asset(id="gem", kind="sprite", source="claude")
        self.assertEqual(manifest.frame_names(still, "gem"), [("idle", 0, "gem")])


if __name__ == "__main__":
    unittest.main()
