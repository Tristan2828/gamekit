import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "gamekit" / "scripts"))

from PIL import Image  # noqa: E402

from gamekit_lib import audio, cli, manifest  # noqa: E402

HERO = """frames:
  idle:
    - |
      kk
      kk
    - |
      ww
      ww
  walk:
    - |
      kw
      wk
    - |
      wk
      kw
  attack:
    - |
      ww
      kk
"""


class FrameFilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._cwd = os.getcwd()
        os.chdir(self.root)
        (self.root / "palette.hex").write_text("000000 k\nffffff w\n", encoding="utf-8")
        (self.root / "art").mkdir()
        (self.root / "art" / "hero.yaml").write_text(HERO, encoding="utf-8")

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def write_manifest(self, extra: str = "", frames: str = "{idle: 2, walk: 2, attack: 1}") -> manifest.Manifest:
        (self.root / "assets.yaml").write_text(
            "palette: palette.hex\noutput: assets\nframe_files: true\n" + extra + "assets:\n"
            f"  - {{id: hero, kind: sprite, source: claude, file: art/hero.png, size: [2, 2], frames: {frames}}}\n",
            encoding="utf-8")
        return manifest.load(self.root / "assets.yaml")

    def run_cli(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = cli.main(list(args))
        return code, out.getvalue()

    def test_frame_names_follow_the_game_convention(self) -> None:
        loaded = self.write_manifest()
        names = [p.name for _, _, p in loaded.frame_paths(loaded.assets[0])]
        self.assertEqual(names, ["hero.png", "hero_1.png", "hero_walk_1.png", "hero_walk_2.png", "hero_attack.png"])

    def test_draw_writes_one_file_per_frame_and_checks(self) -> None:
        self.write_manifest()
        code, out = self.run_cli("draw", "--all")
        self.assertEqual(code, 0, out)
        folder = self.root / "assets" / "art"
        self.assertEqual(sorted(p.name for p in folder.iterdir()),
                         ["hero.png", "hero_1.png", "hero_attack.png", "hero_walk_1.png", "hero_walk_2.png"])
        with Image.open(folder / "hero_walk_1.png") as img:
            self.assertEqual(img.getpixel((1, 0)), (255, 255, 255, 255))
        self.assertEqual(self.run_cli("check")[0], 0)
        self.assertEqual(self.run_cli("preview")[0], 0)

        (folder / "hero_walk_2.png").unlink()
        Image.new("RGBA", (3, 2), (0, 0, 0, 255)).save(folder / "hero_1.png")
        code, out = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("missing frame files hero_walk_2.png", out)
        self.assertIn("hero_1.png is 3x2", out)

    def test_frames_need_idle(self) -> None:
        loaded = self.write_manifest(frames="{walk: 2}")
        self.assertTrue(any("need an idle animation" in p for p in manifest.validate(loaded, check_files=False)))

    def test_audio_levels_from_manifest(self) -> None:
        (self.root / "assets.yaml").write_text(
            "audio: {sfx_peak_db: -3, music_lufs: -16}\nassets:\n"
            "  - {id: coin, kind: sfx, source: sfxr, file: sfx/coin.wav}\n", encoding="utf-8")
        loaded = manifest.load(self.root / "assets.yaml")
        self.assertEqual((loaded.sfx_peak_db, loaded.music_lufs), (-3.0, -16.0))
        self.assertEqual(self.run_cli("sfx", "new", "coin", "--preset", "pickup")[0], 0)
        info = audio.describe(audio.read(self.root / "assets" / "sfx" / "coin.wav"))
        self.assertAlmostEqual(info.peak_db, -3.0, delta=0.1)

    def test_bad_audio_block(self) -> None:
        (self.root / "assets.yaml").write_text("audio: {sfx_peak_db: 3, loud: 1}\nassets: []\n", encoding="utf-8")
        problems = manifest.validate(manifest.load(self.root / "assets.yaml"))
        self.assertTrue(any("unknown keys ['loud']" in p for p in problems))
        self.assertTrue(any("audio.sfx_peak_db" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
