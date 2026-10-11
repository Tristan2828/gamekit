import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "gamekit" / "scripts"))

from gamekit_lib import cli, palette  # noqa: E402

TEMPLATES = Path(__file__).resolve().parent.parent / "plugins" / "gamekit" / "templates"


class PaletteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_template_palette_loads(self) -> None:
        self.assertEqual(len(palette.load(TEMPLATES / "palette.hex")), 16)

    def test_hex_with_hashes_and_comments(self) -> None:
        path = self.folder / "p.hex"
        path.write_text("; comment\n#FF0000\n\n// note\n00ff00\n", encoding="utf-8")
        self.assertEqual(palette.load(path), [(255, 0, 0), (0, 255, 0)])

    def test_gpl(self) -> None:
        path = self.folder / "p.gpl"
        path.write_text("GIMP Palette\nName: test\n#\n255   0   0\tRed\n  0   0 255\n", encoding="utf-8")
        self.assertEqual(palette.load(path), [(255, 0, 0), (0, 0, 255)])

    def test_bad_line_reports_line_number(self) -> None:
        path = self.folder / "p.hex"
        path.write_text("ff0000\nnope\n", encoding="utf-8")
        with self.assertRaisesRegex(palette.PaletteError, ":2:"):
            palette.load(path)


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        self._cwd = os.getcwd()
        os.chdir(self.folder)

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def run_cli(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = cli.main(list(args))
        return code, out.getvalue()

    def test_init_validate_status_credits(self) -> None:
        code, _ = self.run_cli("init", "--game", "Demo")
        self.assertEqual(code, 0)
        self.assertIn("game: Demo", (self.folder / "assets.yaml").read_text(encoding="utf-8"))
        self.assertTrue((self.folder / "palette.hex").exists())

        code, out = self.run_cli("validate")
        self.assertEqual(code, 0, out)
        self.assertIn("16 colors", out)

        code, out = self.run_cli("status", "--todo")
        self.assertEqual(code, 0)
        self.assertIn("0% done", out)
        self.assertIn("sprite hero 16x16", out)

        code, _ = self.run_cli("credits")
        self.assertEqual(code, 0)
        self.assertIn("No finished assets yet.", (self.folder / "CREDITS.md").read_text(encoding="utf-8"))

    def test_init_never_overwrites(self) -> None:
        (self.folder / "assets.yaml").write_text("game: Mine\nassets: []\n", encoding="utf-8")
        self.run_cli("init")
        self.assertEqual((self.folder / "assets.yaml").read_text(encoding="utf-8"), "game: Mine\nassets: []\n")

    def test_missing_manifest_is_a_clean_error(self) -> None:
        code, out = self.run_cli("status")
        self.assertEqual(code, 1)
        self.assertIn("gamekit init", out)

    def test_validate_fails_on_problems(self) -> None:
        (self.folder / "assets.yaml").write_text(
            "assets:\n  - {id: x, kind: sfx, source: sfxr, file: x.mp3}\n", encoding="utf-8")
        code, out = self.run_cli("validate")
        self.assertEqual(code, 1)
        self.assertIn("1 problem", out)


if __name__ == "__main__":
    unittest.main()
