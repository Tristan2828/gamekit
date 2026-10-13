import json
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

from gamekit_lib import audio, engines, manifest, ui  # noqa: E402

# Plays the sound and voice models: same protocol, writes a short tone (with silence around it).
FAKE_WORKER = textwrap.dedent('''
    import json, math, struct, sys, wave
    def reply(o):
        sys.stdout.write("@@" + json.dumps(o) + "\\n"); sys.stdout.flush()
    reply({"ready": True})
    for line in sys.stdin:
        r = json.loads(line)
        reply({"step": "Reading" if "text" in r else "Making the sound"})
        rate = 24000
        tone = [int(9000 * math.sin(2 * math.pi * 300 * i / rate)) for i in range(rate // 2)]
        frames = [0] * (rate // 4) + tone + [0] * (rate // 4)
        with wave.open(r["out"], "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
            w.writeframes(b"".join(struct.pack("<h", f) for f in frames))
        reply({"ok": True, "seed": r["seed"], "seconds": 1.0})
''')

MANIFEST = """game: T
audio:
  sfx_peak_db: -3
assets:
  - {id: door, kind: sfx, source: library, status: todo, file: sfx/door.wav}
  - {id: narrator_intro, kind: voice, source: ai, status: todo, file: voice/intro.wav}
  - {id: theme, kind: music, source: synth, file: music/theme.ogg}
"""


class TakeRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "assets.yaml").write_text(MANIFEST, encoding="utf-8")
        script = self.root / "fake.py"
        script.write_text(FAKE_WORKER, encoding="utf-8")
        self.workers = {kind: engines.Worker(engines.get(kind), [sys.executable, "-u", str(script)])
                        for kind in ("sound", "voice")}
        self.patches = [unittest.mock.patch.dict("os.environ", {"GAMEKIT_ENGINES": str(self.root / "engines")}),
                        unittest.mock.patch.object(engines, "worker", lambda name: self.workers[name]),
                        unittest.mock.patch.object(engines, "is_installed", lambda engine: True)]
        for p in self.patches:
            p.start()
        self.server = ui.make_server(self.root / "assets.yaml", 0)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        for w in self.workers.values():
            w.stop()
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

    def run_job(self, path: str, body: dict) -> dict:
        code, data = self.post(path, body)
        self.assertEqual(code, 200, data)
        for _ in range(200):
            job = self.post("/api/job", {})[1]["job"]
            if job and job["state"] != "running":
                return job
            time.sleep(0.05)
        self.fail("the job never finished")

    def test_voices(self) -> None:
        self.assertEqual(self.post("/api/voices/make", {"text": ""})[0], 400)
        self.assertEqual(self.post("/api/voices/make", {"text": "x" * 1501})[0], 400)
        job = self.run_job("/api/voices/make", {"text": "Rest a while, traveller.", "who": "An old storyteller",
                                                "tone": "by a fire", "takes": 2, "seed": 4})
        self.assertEqual(job["result"]["made"], ["rest-a-while-traveller-4.wav", "rest-a-while-traveller-5.wav"])
        takes = self.post("/api/takes", {"kind": "voice"})[1]["takes"]
        meta = {t["name"]: t["meta"] for t in takes}["rest-a-while-traveller-4.wav"]
        self.assertEqual((meta["who"], meta["tone"], meta["language"], meta["seed"]),
                         ("An old storyteller", "by a fire", "English", 4))
        code, data = self.post("/api/takes/use", {"kind": "voice", "name": "rest-a-while-traveller-4.wav",
                                                  "id": "narrator_intro"})
        self.assertEqual(code, 200, data)
        made_file = self.root / "assets" / "voice" / "intro.wav"
        channels, bits, rate, seconds = audio.wav_format(made_file)
        self.assertEqual((channels, bits, rate), (1, 16, 44100))
        self.assertLess(seconds, 0.7)  # the silence around the reading was trimmed
        self.assertEqual(manifest.load(self.root / "assets.yaml").assets[1].status, "draft")

    def test_sounds_and_errors(self) -> None:
        job = self.run_job("/api/sounds/make", {"prompt": "a door slams", "seconds": 1, "takes": 1, "seed": 1, "loop": True})
        name = job["result"]["made"][0]
        self.assertEqual(self.post("/api/takes", {"kind": "sound"})[1]["takes"][0]["meta"]["loop"], True)
        self.assertEqual(self.post("/api/takes", {"kind": "picture"})[0], 400)
        self.assertEqual(self.post("/api/takes/use", {"kind": "sound", "name": name, "id": "theme"})[0], 400)  # .ogg asset
        code, data = self.post("/api/takes/use", {"kind": "sound", "name": name, "id": "door"})
        self.assertEqual(code, 200, data)
        _, _, _, seconds = audio.wav_format(self.root / "assets" / "sfx" / "door.wav")
        self.assertGreater(seconds, 0.9)  # a seamless loop isn't trimmed
        door = manifest.load(self.root / "assets.yaml").assets[0]
        self.assertEqual((door.source, door.status), ("ai", "draft"))
        self.post("/api/takes/remove", {"kind": "sound", "name": name})
        self.assertEqual(self.post("/api/takes", {"kind": "sound"})[1]["takes"], [])

    def test_voice_kind_is_valid(self) -> None:
        self.assertEqual(manifest.validate(manifest.load(self.root / "assets.yaml"), check_files=False), [])


if __name__ == "__main__":
    unittest.main()
