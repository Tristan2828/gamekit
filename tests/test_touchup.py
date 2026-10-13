import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "gamekit" / "scripts"))

from PIL import Image, ImageDraw  # noqa: E402

from gamekit_lib import art, manifest, pictures, pipeline, touchup  # noqa: E402

MANIFEST = """game: T
palette: palette.hex
frame_files: true
sprites:
  outline: "#17121C"
assets:
  - {id: ghoul, kind: sprite, source: claude, status: todo, file: art/ghoul.png, size: [10, 10], frames: {idle: 1, walk: 2}}
  - {id: coin, kind: icon, source: ai, status: draft, file: art/coin.png, size: [8, 8]}
"""


class TouchUpTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "assets.yaml").write_text(MANIFEST, encoding="utf-8")
        (self.root / "palette.hex").write_text("17121c k\n902020 r\nffd959 e\nffffff w\n", encoding="utf-8")
        (self.root / "pictures").mkdir()
        for name, top in (("ghoul-1.png", 20), ("ghoul-2.png", 0)):
            image = Image.new("RGB", (200, 200), "white")
            ImageDraw.Draw(image).rectangle([60, top, 139, top + 159], fill=(150, 30, 30))
            image.save(self.root / "pictures" / name)
        self.m = manifest.load(self.root / "assets.yaml")
        self.ghoul, self.coin = self.m.assets

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def entries(self) -> list:
        return pipeline.palette_entries(self.m)

    def test_text_sprite_uses_the_palette_names(self) -> None:
        image = Image.new("RGBA", (3, 2), (0, 0, 0, 0))
        image.putpixel((0, 0), (0x17, 0x12, 0x1C, 255))
        image.putpixel((1, 0), (0x90, 0x20, 0x20, 255))
        image.putpixel((2, 1), (1, 2, 3, 255))  # not in the palette: gets a spare key, so a keys block lists all
        text = touchup.text_sprite({"": [image]}, self.entries(), True, "test")
        self.assertIn("rows: |\n  kr.\n  ..0\n", text)
        self.assertIn("'0': '010203'", text)
        self.assertIn("'k': '17121c'", text)
        path = self.root / "t.yaml"
        path.write_text(text, encoding="utf-8")
        back, _ = art.render(art.load_text_sprite(path, self.entries()))
        self.assertEqual(back.tobytes(), image.tobytes())  # round trip, pixel for pixel

    def test_drafts_go_to_pictures_not_the_game(self) -> None:
        before = (self.root / "assets.yaml").read_text(encoding="utf-8")
        saved = touchup.drafts(self.m, self.ghoul, {"ghoul": "ghoul-1.png", "ghoul_walk_2": "ghoul-2.png"},
                               every_frame=True)
        self.assertEqual([p.name for p in saved], ["ghoul-1-touchup-10x10.png", "ghoul-1-touchup-10x10-2.png",
                                                   "ghoul-2-touchup-10x10.png"])
        self.assertEqual((self.root / "assets.yaml").read_text(encoding="utf-8"), before)  # the game is untouched
        self.assertFalse((self.root / "art").exists())
        frames = [pictures.read_meta(p)["frame"] for p in saved]
        self.assertEqual(frames, ["ghoul", "ghoul_walk_1", "ghoul_walk_2"])
        self.assertEqual(pictures.read_meta(saved[1])["copy_of"], "ghoul")  # walk_1 had no picture: copies idle
        self.assertTrue(all(pictures.read_meta(p)["touchup"] for p in saved))
        text = saved[0].with_suffix(".yaml")
        self.assertIn("rows: |", text.read_text(encoding="utf-8"))
        # Claude edits the rows; render draws the PNG again from them
        lines = text.read_text(encoding="utf-8").splitlines()
        row = lines.index("rows: |") + 1
        lines[row] = "  w" + lines[row][3:]
        text.write_text("\n".join(lines) + "\n", encoding="utf-8")
        png, problems = touchup.render(self.m, text.name)
        self.assertEqual((png, problems), (saved[0], []))
        with Image.open(png) as image:
            self.assertEqual(image.convert("RGBA").getpixel((0, 0)), (255, 255, 255, 255))
        # only frames with pictures, unless every_frame
        self.assertEqual(len(touchup.drafts(self.m, self.ghoul, {"ghoul_walk_2": "ghoul-2.png"})), 1)

    def test_draft_of_a_still_and_removing_it(self) -> None:
        png = touchup.drafts(self.m, self.coin, {"coin": "ghoul-1.png"})[0]
        self.assertEqual(png.name, "ghoul-1-touchup-8x8.png")
        with Image.open(png) as image:  # used as it is (already the coin's size)
            self.assertEqual(pictures.make_sprite(self.m, self.coin, png.name).tobytes(), image.convert("RGBA").tobytes())
        pictures.remove(self.m, png.name)
        self.assertFalse(png.with_suffix(".yaml").exists())
        self.assertTrue((self.root / "pictures" / "_removed" / png.with_suffix(".yaml").name).exists())
        with self.assertRaisesRegex(touchup.TouchUpError, "no text rows"):
            touchup.render(self.m, "ghoul-1.png")

    def test_sprite_library(self) -> None:
        kept = pictures.save_sprite(self.m, self.ghoul, "ghoul-1.png", frame="ghoul_walk_1")
        self.assertEqual(kept.name, "ghoul-1-sprite-10x10.png")
        meta = pictures.read_meta(kept)
        self.assertEqual((meta["sprite_of"], meta["for"], meta["frame"], meta["width"]),
                         ("ghoul-1.png", "ghoul", "ghoul_walk_1", 10))
        self.assertEqual(pictures.original_of(self.m, kept.name), "ghoul-1.png")
        with Image.open(kept) as image:  # used as it is: not shrunk (or outlined) a second time
            self.assertEqual(pictures.make_sprite(self.m, self.ghoul, kept.name).tobytes(),
                             image.convert("RGBA").tobytes())
        self.assertEqual(pictures.save_sprite(self.m, self.ghoul, "ghoul-1.png").name, "ghoul-1-sprite-10x10-2.png")


if __name__ == "__main__":
    unittest.main()
