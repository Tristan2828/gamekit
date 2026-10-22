"""Inputs that used to crash or reach outside the game folder: names from the page, removed originals,
big unnamed palettes, take numbering."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "gamekit" / "scripts"))

from PIL import Image  # noqa: E402

from gamekit_lib import cli, made, manifest, packs, palette, pictures, touchup, ui  # noqa: E402

MANIFEST = """game: T
assets:
  - {id: hit, kind: sfx, source: sfxr, file: sfx/hit.wav}
  - {id: bat, kind: sprite, source: claude, file: art/bat.png, size: [4, 4]}
"""


class HardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "assets.yaml").write_text(MANIFEST, encoding="utf-8")
        self.loaded = manifest.load(self.root / "assets.yaml")
        self.by_id = {a.id: a for a in self.loaded.assets}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_pack_names_stay_in_packs(self) -> None:
        for name in ("../outside", "/abs", "C:x"):
            with self.assertRaises(packs.PackError):
                packs.load(self.root, name)

    def test_plain_names_refuse_drive_letters(self) -> None:
        with self.assertRaises(made.MadeError):
            made.path_of(self.loaded, "picture", "D:x.png")
        with self.assertRaises(ui.UserError):
            ui.upload_path("D:x.wav")

    def test_take_names_are_plain(self) -> None:
        with self.assertRaises(ui.UserError):
            ui.make_takes(self.loaded, self.by_id["hit"], base_take="../../x/hit_1")
        with self.assertRaises(ui.UserError):
            ui.keep_take(self.loaded, self.by_id["hit"], "../hit_1")

    def test_cli_variants_number_after_existing_takes(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["-m", str(self.root / "assets.yaml"), "sfx", "variants", "hit",
                                       "--preset", "hit", "--count", "2"]), 0)
            self.assertEqual(cli.main(["-m", str(self.root / "assets.yaml"), "sfx", "variants", "hit",
                                       "--preset", "hit", "--count", "2"]), 0)
        names = sorted(p.stem for p in (self.root / "sounds" / "variants").glob("hit_*.yaml"))
        self.assertEqual(names, ["hit_1", "hit_2", "hit_3", "hit_4"])

    def test_original_picture_removed(self) -> None:
        folder = pictures.folder(self.loaded)
        folder.mkdir(parents=True)
        Image.new("RGB", (8, 8)).save(folder / "bat-1-cutout.png")
        pictures.record_cutout(folder / "bat-1-cutout.png", "bat-1.png", {"prompt": "a bat"})
        self.assertEqual(pictures.original_of(self.loaded, "bat-1-cutout.png"), "bat-1-cutout.png")

    def test_status_notes_todo_assets_with_a_file(self) -> None:
        (self.root / "assets" / "art").mkdir(parents=True)
        Image.new("RGBA", (4, 4)).save(self.root / "assets" / "art" / "bat.png")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["-m", str(self.root / "assets.yaml"), "status"])
        self.assertIn("1 todo asset has a file in the game already (bat)", out.getvalue())

    def test_touchup_with_a_big_unnamed_palette(self) -> None:
        entries = [palette.Entry((i * 7, 255 - i * 7, i * 3)) for i in range(32)]  # Lospec style: no names
        image = Image.new("RGBA", (32, 1))
        for x, entry in enumerate(entries):
            image.putpixel((x, 0), (*entry.color, 255))
        text = touchup.text_sprite({"idle": [image]}, entries, True, "test")
        self.assertEqual(text.count("': '"), 32)  # one key per color


if __name__ == "__main__":
    unittest.main()
