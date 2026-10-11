import contextlib
import io
import math
import os
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "gamekit" / "scripts"))

from gamekit_lib import audio, cli, manifest, music  # noqa: E402

HAS_FFMPEG = shutil.which("ffmpeg") is not None


def loop_tone(seconds: float, freq: float = 441.0, amp: float = 0.4) -> list[float]:
    """Whole cycles only, so the end meets the start smoothly."""
    n = int(seconds * audio.RATE)
    return [amp * math.sin(2 * math.pi * freq * i / audio.RATE) for i in range(n)]


class SeamTests(unittest.TestCase):
    def info(self, samples: list[float]) -> music.MusicInfo:
        jump, motion = music.seam(samples)
        head, tail = music.silent_ends(samples)
        return music.MusicInfo(len(samples) / audio.RATE, -16.0, -3.0, jump, motion, head, tail)

    def test_clean_loop(self) -> None:
        self.assertEqual(music.seam_problems("t", self.info(loop_tone(1.0))), [])

    def test_cut_mid_wave_clicks(self) -> None:
        samples = loop_tone(1.0)[: int(audio.RATE * 0.5) + 25]  # stops near a peak
        problems = music.seam_problems("t", self.info(samples))
        self.assertTrue(any("click" in p for p in problems), problems)

    def test_silent_tail_is_a_gap(self) -> None:
        samples = loop_tone(1.0) + [0.0] * int(audio.RATE * 1.5)
        problems = music.seam_problems("t", self.info(samples))
        self.assertTrue(any("silence where it loops" in p for p in problems), problems)


class ManifestMusicTests(unittest.TestCase):
    def test_music_block_and_loop_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "assets.yaml"
            path.write_text("music: {render_script: r.gd, bogus: 1}\nassets:\n"
                            "  - {id: a, kind: music, source: synth, file: a.ogg, loop: maybe}\n"
                            "  - {id: b, kind: sfx, source: sfxr, file: b.wav, loop: true}\n"
                            "  - {id: c, kind: music, source: synth, file: c.ogg, loop: false, replaces: crypt}\n",
                            encoding="utf-8")
            loaded = manifest.load(path)
            problems = manifest.validate(loaded, check_files=False)
            self.assertTrue(any("unknown keys ['bogus']" in p for p in problems))
            self.assertEqual(sum("loop is true / false" in p for p in problems), 2)
            a, _, c = loaded.assets
            self.assertTrue(loaded.loops(a))
            self.assertFalse(loaded.loops(c))
            self.assertEqual((loaded.track_name(a), loaded.track_name(c)), ("a", "crypt"))

    def test_render_command(self) -> None:
        command = music.render_command("godot", Path("/g"), "tools/r.gd", Path("/out"), ["crypt", "boss"])
        self.assertEqual(command[:6], ["godot", "--headless", "--path", "/g", "-s", "tools/r.gd"])
        self.assertEqual(command[-3:], ["--out=/out", "--track=crypt", "--track=boss"])


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg not installed")
class EncodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
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

    def test_encode_loudness_and_cut(self) -> None:
        src = self.root / "song.wav"
        audio.write_wav(src, loop_tone(3.0, amp=0.1))
        out = self.root / "song.ogg"
        music.encode_ogg(src, out, loudness=-16.0)
        self.assertAlmostEqual(music.measure_loudness(out)["input_i"], -16.0, delta=1.0)
        music.encode_ogg(src, out, start=0.5, end=2.0)
        self.assertAlmostEqual(len(audio.read(out)) / audio.RATE, 1.5, delta=0.05)

    def test_loud_peaks_get_limited_to_reach_the_target(self) -> None:
        # Quiet tone with a loud click every 0.5 s: one gain alone would clip before -16 LUFS.
        samples = loop_tone(4.0, amp=0.05)
        for i in range(0, len(samples), audio.RATE // 2):
            samples[i] = 0.9
        src = self.root / "spiky.wav"
        audio.write_wav(src, samples)
        out = self.root / "spiky.ogg"
        note = music.encode_ogg(src, out, loudness=-16.0)
        self.assertIn("peaks limited", note)
        result = music.measure_loudness(out)
        self.assertAlmostEqual(result["input_i"], -16.0, delta=0.6)
        self.assertLess(result["input_tp"], 0.0)

    def test_ogg_sample_count_is_exact(self) -> None:
        for n in (8800, 44100):  # whole cycles of the 441 Hz tone (100 samples each)
            src = self.root / f"t{n}.wav"
            audio.write_wav(src, loop_tone(n / audio.RATE))
            music.encode_ogg(src, self.root / f"t{n}.ogg")
            self.assertEqual(music.ogg_sample_count(self.root / f"t{n}.ogg"), n)
            info = music.describe(self.root / f"t{n}.ogg", loop_source=src)
            self.assertTrue(info.exact)
            self.assertEqual(music.seam_problems("t", info), [])

    def test_clean_command_and_check(self) -> None:
        (self.root / "assets.yaml").write_text(
            "assets:\n  - {id: theme, kind: music, source: library, file: music/theme.ogg}\n", encoding="utf-8")
        src = self.root / "theme.wav"
        audio.write_wav(src, loop_tone(2.0) + [0.0] * int(audio.RATE * 2))
        code, out = self.run_cli("music", "clean", str(src), "theme")
        self.assertEqual(code, 0, out)
        self.assertIn("silence where it loops", out)
        self.assertIn("record where it came from", out)
        code, out = self.run_cli("music", "clean", str(src), "theme", "--end", "2.0", "--force")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.run_cli("check")[0], 0)

    @unittest.skipIf(os.name == "nt", "fake Godot is a shell script")
    def test_render_with_fake_godot(self) -> None:
        (self.root / "project.godot").write_text("", encoding="utf-8")
        (self.root / "tools").mkdir()
        (self.root / "tools" / "render.gd").write_text("", encoding="utf-8")
        (self.root / "assets.yaml").write_text(
            "music: {godot_project: ., render_script: tools/render.gd}\nassets:\n"
            "  - {id: music_crypt, kind: music, source: synth, file: music/crypt.ogg, replaces: crypt}\n",
            encoding="utf-8")
        fake = self.root / "godot"
        # Stands in for Godot running the game's render script: one looping tone per --track.
        fake.write_text(textwrap.dedent(f"""\
            #!{sys.executable}
            import math, sys
            sys.path.insert(0, {str(Path(__file__).resolve().parent.parent / "plugins" / "gamekit" / "scripts")!r})
            from pathlib import Path
            from gamekit_lib import audio
            out = next(a[6:] for a in sys.argv if a.startswith("--out="))
            for a in sys.argv:
                if a.startswith("--track="):
                    samples = [0.4 * math.sin(2 * math.pi * 441 * i / 44100) for i in range(44100)]
                    audio.write_wav(Path(out) / (a[8:] + ".wav"), samples)
            """), encoding="utf-8")
        fake.chmod(0o755)
        old = os.environ.get("GAMEKIT_GODOT")
        os.environ["GAMEKIT_GODOT"] = str(fake)
        try:
            code, out = self.run_cli("music", "render", "--keep-wav", "wavs")
        finally:
            if old is None:
                del os.environ["GAMEKIT_GODOT"]
            else:
                os.environ["GAMEKIT_GODOT"] = old
        self.assertEqual(code, 0, out)
        self.assertIn("music_crypt: rendered -> music/crypt.ogg", out)
        self.assertTrue((self.root / "wavs" / "crypt.wav").exists())
        self.assertEqual(self.run_cli("check")[0], 0)

    def test_render_needs_a_script(self) -> None:
        (self.root / "assets.yaml").write_text(
            "assets:\n  - {id: m, kind: music, source: synth, file: m.ogg}\n", encoding="utf-8")
        old = os.environ.get("GAMEKIT_GODOT")
        os.environ["GAMEKIT_GODOT"] = sys.executable
        try:
            code, out = self.run_cli("music", "render")
        finally:
            if old is None:
                del os.environ["GAMEKIT_GODOT"]
            else:
                os.environ["GAMEKIT_GODOT"] = old
        self.assertEqual(code, 1)
        self.assertIn("music.render_script", out)


if __name__ == "__main__":
    unittest.main()
