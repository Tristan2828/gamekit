import contextlib
import io
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "gamekit" / "scripts"))

from gamekit_lib import audio, cli, sfxr  # noqa: E402


def tone(seconds: float, amp: float = 0.5, freq: float = 440.0) -> list[float]:
    return [amp * math.sin(2 * math.pi * freq * i / audio.RATE) for i in range(int(seconds * audio.RATE))]


class AudioTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_wav_round_trip(self) -> None:
        path = self.root / "a.wav"
        audio.write_wav(path, tone(0.1))
        self.assertEqual(audio.wav_format(path)[:3], (1, 16, 44100))
        back = audio.read(path)
        self.assertEqual(len(back), 4410)
        self.assertAlmostEqual(max(back), 0.5, places=2)

    def test_clean_trims_normalizes_and_fades(self) -> None:
        samples = [0.0] * 4410 + tone(0.1, amp=0.2) + [0.0] * 4410
        out = audio.clean(samples)
        self.assertLess(len(out), 4410 + 2 * 300)
        self.assertAlmostEqual(max(abs(s) for s in out), audio.db_to_gain(-1.0), places=2)
        self.assertEqual(out[-1], 0.0)

    def test_clean_matches_reference_loudness_and_cuts(self) -> None:
        reference = tone(0.2, amp=0.05)
        loud = tone(1.0, amp=0.8)
        out = audio.clean(loud, peak_db=-3.0, match=reference, max_seconds=0.5)
        self.assertLessEqual(len(out), int(0.5 * audio.RATE))
        self.assertAlmostEqual(audio.rms(out[:2000]), audio.rms(reference), delta=0.005)
        # A quiet sound matched to a loud reference stops at the peak ceiling.
        out = audio.clean(tone(0.2, amp=0.01), peak_db=-3.0, match=tone(0.2, amp=0.9))
        self.assertAlmostEqual(max(abs(s) for s in out), audio.db_to_gain(-3.0), places=2)

    def test_silence_is_an_error(self) -> None:
        with self.assertRaisesRegex(audio.AudioError, "silent"):
            audio.clean([0.0] * 100)

    def test_resample_length(self) -> None:
        self.assertEqual(len(audio.resample([0.0] * 22050, 22050, 44100)), 44100)

    def test_describe(self) -> None:
        info = audio.describe(tone(0.5, amp=1.0, freq=1000))
        self.assertAlmostEqual(info.seconds, 0.5, places=2)
        self.assertAlmostEqual(info.brightness, 2000, delta=20)  # two zero crossings per cycle
        self.assertGreater(info.clipped, 0)
        self.assertEqual(len(audio.envelope_bar(info.envelope)), len(info.envelope))

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_ffmpeg_decodes_ogg(self) -> None:
        src = self.root / "a.wav"
        audio.write_wav(src, tone(0.2))
        ogg = self.root / "a.ogg"
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-c:a", "libvorbis", str(ogg)], check=True)
        self.assertAlmostEqual(len(audio.read(ogg)) / audio.RATE, 0.2, delta=0.05)  # encoder padding

    def test_missing_ffmpeg_message(self) -> None:
        old = os.environ.get("GAMEKIT_FFMPEG")
        os.environ["GAMEKIT_FFMPEG"] = "/nope/ffmpeg"
        try:
            with self.assertRaisesRegex(audio.AudioError, "doesn't exist"):
                audio.find_ffmpeg()
        finally:
            if old is None:
                del os.environ["GAMEKIT_FFMPEG"]
            else:
                os.environ["GAMEKIT_FFMPEG"] = old


class SfxrTests(unittest.TestCase):
    def test_every_preset_renders_sound(self) -> None:
        for name in sfxr.PRESETS:
            samples = sfxr.render(sfxr.preset(name, 3))
            self.assertGreater(len(samples), 100, name)
            self.assertGreater(max(abs(s) for s in samples), 0.001, name)

    def test_deterministic(self) -> None:
        a = sfxr.render(sfxr.preset("explosion", 7))
        b = sfxr.render(sfxr.preset("explosion", 7))
        self.assertEqual(a, b)
        self.assertNotEqual(a, sfxr.render(sfxr.preset("explosion", 8)))

    def test_square_pitch(self) -> None:
        # base_freq 0.5 -> period 100/(0.25+0.001) ~ 398 supersamples -> ~49.75 samples -> ~886 Hz
        p = sfxr.Params(base_freq=0.5, env_sustain=0.5, env_decay=0.0)
        info = audio.describe(sfxr.render(p))
        self.assertAlmostEqual(info.brightness / 2, 886, delta=30)

    def test_clamp_and_file_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.yaml"
            sfxr.save(path, sfxr.Params(base_freq=2.0, freq_ramp=-3.0, wave="saw"), "laser")
            loaded = sfxr.load(path)
            self.assertEqual((loaded.base_freq, loaded.freq_ramp, loaded.wave), (1.0, -1.0, "saw"))
            path.write_text("wave: square\nbogus: 1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "bogus"):
                sfxr.load(path)

    def test_mutate_changes_a_little(self) -> None:
        base = sfxr.preset("pickup", 1)
        changed = sfxr.mutate(base, seed=5, amount=0.05)
        self.assertEqual(changed.wave, base.wave)
        self.assertLessEqual(abs(changed.base_freq - base.base_freq), 0.05 + 1e-9)


class SfxCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._cwd = os.getcwd()
        os.chdir(self.root)
        (self.root / "assets.yaml").write_text(
            "game: T\noutput: assets\nassets:\n"
            "  - {id: coin, kind: sfx, source: sfxr, file: sfx/coin.wav}\n"
            "  - {id: door, kind: sfx, source: library, file: sfx/door.wav}\n", encoding="utf-8")

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def run_cli(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = cli.main(list(args))
        return code, out.getvalue()

    def test_new_variants_make_check(self) -> None:
        code, out = self.run_cli("sfx", "new", "coin", "--preset", "pickup", "--seed", "4")
        self.assertEqual(code, 0, out)
        self.assertIn("shape |", out)
        self.assertTrue((self.root / "sounds" / "coin.yaml").exists())
        self.assertEqual(audio.wav_format(self.root / "assets" / "sfx" / "coin.wav")[:3], (1, 16, 44100))
        self.assertIn("--force", self.run_cli("sfx", "new", "coin", "--preset", "pickup")[1])

        code, out = self.run_cli("sfx", "variants", "coin", "--count", "2")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / "sounds" / "variants" / "coin_2.wav").exists())
        code, out = self.run_cli("sfx", "new", "coin", "--from", "sounds/variants/coin_2.yaml", "--force")
        self.assertEqual(code, 0, out)

        self.assertEqual(self.run_cli("sfx", "make")[0], 0)
        code, out = self.run_cli("check")
        self.assertEqual(code, 0, out)
        self.assertIn("checked 1 file", out)

    def test_clean_and_check_flags_stereo(self) -> None:
        raw = self.root / "door_raw.wav"
        with wave.open(str(raw), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(44100)
            w.writeframes(bytes(400) + b"\x00\x40\x00\x40" * 2000 + bytes(400))
        (self.root / "assets" / "sfx").mkdir(parents=True)
        shutil.copy(raw, self.root / "assets" / "sfx" / "door.wav")
        code, out = self.run_cli("check", "door")
        self.assertEqual(code, 1)
        self.assertIn("mono", out)
        code, out = self.run_cli("sfx", "clean", str(raw), "door", "--force")
        self.assertEqual(code, 0, out)
        self.assertIn("record where it came from", out)
        self.assertEqual(self.run_cli("check", "door")[0], 0)

    def test_info_by_id_and_path(self) -> None:
        self.run_cli("sfx", "new", "coin", "--preset", "blip")
        code, out = self.run_cli("sfx", "info", "coin", "assets/sfx/coin.wav")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("peak"), 2)


if __name__ == "__main__":
    unittest.main()
