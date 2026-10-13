import json
import shutil
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import unittest.mock
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "gamekit" / "scripts"))

from gamekit_lib import audio, engines, made, manifest, ui  # noqa: E402

# Plays the music model: same protocol, writes a few seconds of a quiet tone instead of composing.
FAKE_WORKER = textwrap.dedent('''
    import json, math, struct, sys, wave
    def reply(o):
        sys.stdout.write("@@" + json.dumps(o) + "\\n"); sys.stdout.flush()
    reply({"ready": True})
    for line in sys.stdin:
        r = json.loads(line)
        reply({"step": "Composing"})
        rate, seconds = 44100, min(3, r["seconds"])
        with wave.open(r["out"], "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
            w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 220 * i / rate)))
                                   for i in range(rate * seconds)))
        reply({"ok": True, "seed": r["seed"], "seconds": r["seconds"], "planner": r.get("planner", False)})
''')

MANIFEST = """game: T
audio:
  music_lufs: -16
assets:
  - {id: crypt, kind: music, source: synth, status: todo, file: music/crypt.ogg}  # the crypt theme
  - {id: hit, kind: sfx, source: sfxr, file: sfx/hit.wav}
"""


class MusicTakePageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "assets.yaml").write_text(MANIFEST, encoding="utf-8")
        script = self.root / "fake_music.py"
        script.write_text(FAKE_WORKER, encoding="utf-8")
        fake = engines.Worker(engines.get("music"), [sys.executable, "-u", str(script)])
        self.fake = fake
        self.patches = [unittest.mock.patch.dict("os.environ", {"GAMEKIT_ENGINES": str(self.root / "engines")}),
                        unittest.mock.patch.object(engines, "worker", lambda name: fake),
                        unittest.mock.patch.object(engines, "is_installed", lambda engine: True)]
        for p in self.patches:
            p.start()
        self.server = ui.make_server(self.root / "assets.yaml", 0)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.fake.stop()
        for p in self.patches:
            p.stop()
        ui.CURRENT["job"] = None
        self._tmp.cleanup()

    def post(self, path: str, body: dict) -> tuple[int, dict]:
        request = urllib.request.Request(self.base + path, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "X-Gamekit": "1"})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def make_takes(self) -> list[str]:
        code, _ = self.post("/api/musictakes/make", {"prompt": "Tense dungeon music", "seconds": 30, "bpm": 70,
                                                     "key": "D minor", "takes": 2, "seed": 5})
        self.assertEqual(code, 200)
        for _ in range(200):
            job = self.post("/api/job", {})[1]["job"]
            if job and job["state"] != "running":
                break
            time.sleep(0.05)
        self.assertEqual(job["state"], "done", job)
        return job["result"]["made"]

    def test_make_keep_remove(self) -> None:
        self.assertEqual(self.post("/api/musictakes/make", {"prompt": " "})[0], 400)
        names = self.make_takes()
        self.assertEqual(names, ["tense-dungeon-music-5.wav", "tense-dungeon-music-6.wav"])
        takes = self.post("/api/musictakes", {})[1]["takes"]
        meta = {t["name"]: t["meta"] for t in takes}["tense-dungeon-music-5.wav"]
        self.assertEqual((meta["bpm"], meta["key"], meta["seconds"], meta["instrumental"]), (70, "D minor", 30, True))
        self.assertTrue(all(t["url"].startswith("/file/music-takes/") for t in takes))
        self.post("/api/musictakes/keep", {"name": names[0]})
        self.assertTrue(made.read_meta(made.folder(manifest.load(self.root / "assets.yaml"), "music") / names[0])["kept"])
        self.post("/api/musictakes/remove", {"name": names[1]})
        self.assertEqual(len(self.post("/api/musictakes", {})[1]["takes"]), 1)
        self.assertEqual(self.post("/api/musictakes/remove", {"name": "../assets.yaml"})[0], 400)

    def test_use_for_a_track(self) -> None:
        try:
            audio.find_ffmpeg()
        except audio.AudioError:
            self.skipTest("needs ffmpeg")
        name = self.make_takes()[0]
        self.assertEqual(self.post("/api/musictakes/use", {"name": name, "id": "hit"})[0], 400)  # not music
        code, data = self.post("/api/musictakes/use", {"name": name, "id": "crypt", "start": 0.5, "end": 2.5})
        self.assertEqual(code, 200, data)
        self.assertEqual((self.root / "assets" / "music" / "crypt.ogg").read_bytes()[:4], b"OggS")
        crypt = manifest.load(self.root / "assets.yaml").assets[0]
        self.assertEqual((crypt.source, crypt.status), ("ai", "draft"))
        self.assertIn("# the crypt theme", (self.root / "assets.yaml").read_text(encoding="utf-8"))
        code, data = self.post("/api/musictakes/use", {"name": name, "id": "crypt"})
        self.assertEqual((code, data["error"]), (400, "REPLACE?"))


class EngineSetupTests(unittest.TestCase):
    def test_setup_steps_for_an_engine_with_code(self) -> None:
        """setup() clones the engine's code at its commit and installs its requirements file; the commands are
        recorded rather than run."""
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.dict("os.environ", {"GAMEKIT_ENGINES": tmp, "GAMEKIT_TORCH": "cpu"}), \
                unittest.mock.patch.object(engines, "find_uv", lambda: "uv"), \
                unittest.mock.patch.object(engines.shutil, "which", lambda name: name):
            ran: list[list[str]] = []
            steps = engines.setup("music", run=ran.append)
            for _ in range(6):  # up to "Installing the model's libraries"; the PyTorch check needs a real Python
                next(steps)
            next(steps, None)
            flat = [" ".join(c) for c in ran]
            self.assertTrue(any(c.startswith("uv venv --python 3.12") for c in flat))
            self.assertTrue(any("clone" in c and "ACE-Step-1.5" in c for c in flat))
            self.assertTrue(any("checkout" in c and engines.ENGINES["music"].code[1] in c for c in flat))
            self.assertTrue(any(c.endswith("requirements.txt") and " -r " in c for c in flat))  # cpu -> the "*" file
            env = engines.worker_env(engines.get("music"))
            self.assertEqual(env["ACESTEP_LM_BACKEND"], "pt")
            self.assertTrue(env["GAMEKIT_ENGINE_CODE"].endswith(str(Path("code") / "music")))


if __name__ == "__main__":
    unittest.main()
