import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "gamekit" / "scripts"))

from PIL import Image  # noqa: E402

from gamekit_lib import cli, credits, manifest, packs  # noqa: E402

RED, BLUE = (200, 30, 30), (20, 40, 200)


def make_sheet(path: Path) -> None:
    """A 32x16 sheet: two 8x8 frames on the top row (red, blue), a half-transparent pixel."""
    image = Image.new("RGBA", (32, 16), (0, 0, 0, 0))
    for x in range(8):
        for y in range(8):
            image.putpixel((x, y), (*RED, 255))
            image.putpixel((x + 8, y), (*BLUE, 255))
    image.putpixel((20, 4), (210, 40, 35, 100))
    image.save(path)


class PackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.download = self.root / "download"
        self.download.mkdir()
        self._cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def run_cli(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = cli.main(list(args))
        return code, out.getvalue()

    def make_zip(self, entries: dict[str, bytes], name: str = "pack.zip") -> Path:
        path = self.download / name
        with zipfile.ZipFile(path, "w") as z:
            for member, data in entries.items():
                z.writestr(member, data)
        return path

    def write_manifest(self, assets: str) -> None:
        (self.root / "palette.hex").write_text("c81e1e r\n1428c8 b\n000000 k\n", encoding="utf-8")
        (self.root / "assets.yaml").write_text(
            "game: T\noutput: assets\npalette: palette.hex\nassets:\n" + assets, encoding="utf-8")

    def test_add_zip_flattens_and_finds_license_hints(self) -> None:
        sheet = self.root / "sheet.png"
        make_sheet(sheet)
        archive = self.make_zip({
            "Tiny Pack/License.txt": b"This pack is released under Creative Commons Zero (CC0).",
            "Tiny Pack/sprites/sheet.png": sheet.read_bytes(),
            "__MACOSX/._junk": b"x",
        })
        code, out = self.run_cli("pack", "add", str(archive), "tiny")
        self.assertEqual(code, 0, out)
        self.assertIn("license: NOT SET", out)
        self.assertIn("License.txt: CC0 / public domain", out)
        pack = packs.load(self.root, "tiny")
        self.assertEqual([p.as_posix() for p in packs.list_files(pack)], ["License.txt", "sprites/sheet.png"])
        self.assertEqual(pack.license_file, "License.txt")
        self.assertFalse(pack.has_license())

    def test_unsafe_zip_is_refused_and_cleaned_up(self) -> None:
        archive = self.make_zip({"../evil.txt": b"x"})
        code, out = self.run_cli("pack", "add", str(archive), "bad")
        self.assertEqual(code, 1)
        self.assertIn("unsafe path", out)
        self.assertFalse((self.root / "packs" / "bad").exists())
        self.assertFalse((self.root / "evil.txt").exists())

    def test_add_refuses_existing_pack_and_bad_names(self) -> None:
        (self.download / "a.png").write_bytes(b"")
        self.assertEqual(self.run_cli("pack", "add", str(self.download), "p")[0], 0)
        code, out = self.run_cli("pack", "add", str(self.download), "p")
        self.assertEqual(code, 1)
        self.assertIn("already exists", out)
        self.assertIn("lowercase", self.run_cli("pack", "add", str(self.download), "Bad Name")[1])

    def test_use_needs_a_license(self) -> None:
        make_sheet(self.download / "sheet.png")
        self.write_manifest("  - {id: hero, kind: sprite, source: pack, file: hero.png, size: [8, 8]}\n")
        self.run_cli("pack", "add", str(self.download), "p")
        code, out = self.run_cli("pack", "use", "p", "sheet.png", "hero", "--crop", "0,0,8,8")
        self.assertEqual(code, 1)
        self.assertIn("no license", out)

    def test_use_crop_anim_resize_recolor_and_credits(self) -> None:
        make_sheet(self.download / "sheet.png")
        self.write_manifest(
            "  - {id: block, kind: icon, source: pack, status: draft, file: icons/block.png, size: [16, 16],"
            " license: {pack: p}}\n"
            "  - {id: hero, kind: sprite, source: pack, status: draft, file: hero.png, size: [8, 8],"
            " frames: {walk: 2}, license: {pack: p}}\n")
        code, out = self.run_cli("pack", "add", str(self.download), "p", "--license", "CC-BY 4.0",
                                 "--author", "Ada", "--license-url", "https://example.com")
        self.assertEqual(code, 0, out)

        code, out = self.run_cli("pack", "use", "p", "sheet.png", "block", "--crop", "0,0,8,8",
                                 "--resize", "16x16")
        self.assertEqual(code, 0, out)
        with Image.open(self.root / "assets" / "icons" / "block.png") as block:
            self.assertEqual(block.size, (16, 16))
        self.assertNotIn("off-palette", out)

        code, out = self.run_cli("pack", "use", "p", "sheet.png", "hero", "--anim", "walk=0,0,2")
        self.assertEqual(code, 0, out)
        side = json.loads((self.root / "assets" / "hero.json").read_text(encoding="utf-8"))
        self.assertEqual(side["animations"], {"walk": [[0, 0], [8, 0]]})
        with Image.open(self.root / "assets" / "hero.png") as hero:
            self.assertEqual(hero.getpixel((8, 0)), (*BLUE, 255))

        code, out = self.run_cli("pack", "use", "p", "sheet.png", "hero", "--anim", "walk=0,0,2")
        self.assertIn("--force", out)

        self.assertEqual(self.run_cli("validate")[0], 0)
        text = credits.render(manifest.load(self.root / "assets.yaml"))
        self.assertIn("**Ada**, CC-BY 4.0 ([source](https://example.com)): block, hero", text)

    def test_recolor_snaps_and_clean_alpha(self) -> None:
        image = Image.new("RGBA", (3, 1), (0, 0, 0, 0))
        image.putpixel((0, 0), (190, 40, 35, 255))
        image.putpixel((1, 0), (30, 50, 190, 255))
        image.putpixel((2, 0), (190, 40, 35, 60))
        cleaned = packs.clean_alpha(image)
        self.assertEqual(cleaned.getpixel((2, 0)), (0, 0, 0, 0))
        recolored, changed = packs.recolor(cleaned, [RED, BLUE])
        self.assertEqual(changed, 2)
        self.assertEqual(recolored.getpixel((0, 0)), (*RED, 255))
        self.assertEqual(recolored.getpixel((1, 0)), (*BLUE, 255))

    def test_crop_outside_image_and_bad_flags(self) -> None:
        image = Image.new("RGBA", (8, 8))
        with self.assertRaisesRegex(packs.PackError, "outside"):
            packs.crop(image, (4, 4, 8, 8))
        with self.assertRaises(packs.PackError):
            packs.parse_anim("walk=0,0")
        with self.assertRaises(packs.PackError):
            packs.parse_box("1,2,3")

    def test_validate_reports_missing_pack_license(self) -> None:
        (self.download / "a.png").write_bytes(b"")
        self.run_cli("pack", "add", str(self.download), "p")
        self.write_manifest("  - {id: x, kind: icon, source: pack, status: draft, file: x.png, size: [8, 8],"
                            " license: {pack: p}}\n"
                            "  - {id: y, kind: icon, source: pack, status: draft, file: y.png, size: [8, 8],"
                            " license: {pack: nope}}\n")
        code, out = self.run_cli("validate", "--no-files")
        self.assertEqual(code, 1)
        self.assertIn("license.name (e.g. CC0, CC-BY 4.0) in its pack.yaml", out)
        self.assertIn("no pack named 'nope'", out)

    def test_audio_from_pack_is_cleaned(self) -> None:
        import math
        import wave
        with wave.open(str(self.download / "boom.wav"), "wb") as w:  # stereo 22050 Hz with silence around
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(22050)
            frames = bytearray(4 * 2000)
            for i in range(2000):
                v = int(8000 * math.sin(i / 5)).to_bytes(2, "little", signed=True)
                frames += v + v
            w.writeframes(bytes(frames) + bytes(4 * 2000))
        (self.download / "notes.txt").write_text("x", encoding="utf-8")
        self.write_manifest("  - {id: boom, kind: sfx, source: library, file: sfx/boom.wav}\n")
        self.run_cli("pack", "add", str(self.download), "s", "--license", "CC0", "--author", "Kenney")
        code, out = self.run_cli("pack", "use", "s", "notes.txt", "boom")
        self.assertEqual(code, 1)
        self.assertIn("not a sound file", out)
        code, out = self.run_cli("pack", "use", "s", "boom.wav", "boom")
        self.assertEqual(code, 0, out)
        with wave.open(str(self.root / "assets" / "sfx" / "boom.wav"), "rb") as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, 44100))
            self.assertLess(w.getnframes(), 4500)  # 2000 samples at 22050 Hz -> ~4000, silence trimmed
        self.assertIn("source: pack, status: draft, license: {pack: s}", out)

    def test_use_refuses_paths_outside_pack(self) -> None:
        (self.download / "a.png").write_bytes(b"")
        self.write_manifest("  - {id: x, kind: icon, source: pack, file: x.png, size: [8, 8]}\n")
        self.run_cli("pack", "add", str(self.download), "p", "--license", "CC0", "--author", "A")
        code, out = self.run_cli("pack", "use", "p", "../../assets.yaml", "x")
        self.assertEqual(code, 1)
        self.assertIn("is not a file in pack", out)


if __name__ == "__main__":
    unittest.main()
