import contextlib
import io
import json
import shutil
import sys
import tempfile
import threading
import unittest
import unittest.mock
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "gamekit" / "scripts"))

from gamekit_lib import manifest, sfxr, ui  # noqa: E402

TEMPLATES = Path(__file__).resolve().parent.parent / "plugins" / "gamekit" / "templates"

FLOW = """# my game
game: Test
assets:
  # --- heroes ---
  - {id: hero, kind: sprite, source: claude, status: todo, file: art/hero.png, size: [8, 8]}  # the player
  - {id: hero_two, kind: sprite, source: claude, file: art/hero_two.png, size: [8, 8]}
"""


class SetStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "assets.yaml"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_flow_entries_keep_comments(self) -> None:
        self.path.write_text(FLOW, encoding="utf-8")
        manifest.set_status(self.path, "hero", "draft")
        manifest.set_status(self.path, "hero_two", "done")  # no status yet: added after the id
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("{id: hero, kind: sprite, source: claude, status: draft,", text)
        self.assertIn("{id: hero_two, status: done, kind: sprite", text)
        self.assertIn("# --- heroes ---", text)
        self.assertIn("# the player", text)
        statuses = {a.id: a.status for a in manifest.load(self.path).assets}
        self.assertEqual(statuses, {"hero": "draft", "hero_two": "done"})

    def test_block_entries_and_line_endings(self) -> None:
        text = (TEMPLATES / "assets.yaml").read_text(encoding="utf-8").replace("\n", "\r\n")
        text = text.replace("    status: todo\r\n    file: sfx/hit.wav", "    file: sfx/hit.wav  # no status")
        self.path.write_bytes(text.encode("utf-8"))
        manifest.set_status(self.path, "hero", "done")
        manifest.set_status(self.path, "hit", "draft")
        raw = self.path.read_bytes().decode("utf-8")
        self.assertNotIn("\r\r", raw)
        self.assertEqual(raw.count("\n"), raw.count("\r\n"))  # still CRLF everywhere
        self.assertIn("# Asset manifest", raw)
        statuses = {a.id: a.status for a in manifest.load(self.path).assets}
        self.assertEqual(statuses, {"hero": "done", "hit": "draft"})

    def test_unknown_id_and_status(self) -> None:
        self.path.write_text(FLOW, encoding="utf-8")
        with self.assertRaises(manifest.ManifestError):
            manifest.set_status(self.path, "nobody", "done")
        with self.assertRaises(manifest.ManifestError):
            manifest.set_status(self.path, "hero", "finished")
        self.assertEqual(self.path.read_text(encoding="utf-8"), FLOW)

    def test_similar_ids_are_not_confused(self) -> None:
        self.path.write_text(FLOW, encoding="utf-8")
        manifest.set_status(self.path, "hero", "done")
        statuses = {a.id: a.status for a in manifest.load(self.path).assets}
        self.assertEqual(statuses["hero_two"], "todo")


class TweakTests(unittest.TestCase):
    def test_every_tweak_changes_the_sound(self) -> None:
        base = sfxr.tweak(sfxr.preset("laser", 3), "wobble")  # has vibrato and a high-pass, so every word applies
        self.assertTrue(base.vib_strength and base.hpf_freq)
        for word in sfxr.TWEAKS:
            self.assertNotEqual(sfxr.tweak(base, word), base, word)

    def test_directions(self) -> None:
        base = sfxr.preset("hit", 1)
        self.assertGreater(sfxr.tweak(base, "higher").base_freq, base.base_freq)
        self.assertLess(sfxr.tweak(base, "shorter").env_decay, base.env_decay)
        self.assertEqual(sfxr.tweak(base, "punchier").env_attack, 0.0)
        with self.assertRaises(ValueError):
            sfxr.tweak(base, "louder")


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        shutil.copyfile(TEMPLATES / "assets.yaml", self.root / "assets.yaml")
        shutil.copyfile(TEMPLATES / "palette.hex", self.root / "palette.hex")
        (self.root / "secret.txt").write_text("no", encoding="utf-8")
        self.server = ui.make_server(self.root / "assets.yaml", 0)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self._tmp.cleanup()

    def get(self, path: str, headers: dict | None = None) -> tuple[int, bytes]:
        request = urllib.request.Request(self.base + path, headers=headers or {})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def post(self, path: str, body: dict, header: bool = True) -> tuple[int, dict]:
        headers = {"Content-Type": "application/json"} | ({"X-Gamekit": "1"} if header else {})
        request = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_state_and_page(self) -> None:
        code, body = self.get("/api/state")
        self.assertEqual(code, 200)
        data = json.loads(body)
        self.assertEqual([a["id"] for a in data["assets"]], ["hero", "hit"])
        self.assertEqual(data["counts"], {"todo": 2, "draft": 0, "done": 0})
        self.assertEqual(self.get("/")[0], 200)

    def test_status_change_writes_the_manifest(self) -> None:
        code, _ = self.post("/api/status", {"id": "hero", "status": "draft"})
        self.assertEqual(code, 200)
        self.assertEqual(manifest.load(self.root / "assets.yaml").assets[0].status, "draft")
        code, data = self.post("/api/status", {"id": "nobody", "status": "draft"})
        self.assertEqual(code, 400)
        self.assertIn("nobody", data["error"])

    def test_guards(self) -> None:
        self.assertEqual(self.post("/api/status", {"id": "hero", "status": "done"}, header=False)[0], 403)
        self.assertEqual(self.get("/api/state", {"Host": "evil.example"})[0], 403)
        self.assertEqual(self.get("/file/..%2F..%2Fwindows")[0], 404)
        self.assertEqual(self.get("/file/secret.txt")[0], 200)  # inside the game folder is fine
        self.assertEqual(self.get("/file/../" + self.root.name + "/secret.txt")[0], 200)
        self.assertEqual(manifest.load(self.root / "assets.yaml").assets[0].status, "todo")

    def test_sound_takes_keep_and_clear(self) -> None:
        code, data = self.post("/api/sfx/make", {"id": "hit", "preset": "hit", "count": 2})
        self.assertEqual((code, data["made"]), (200, ["hit_1", "hit_2"]))
        code, data = self.post("/api/sfx/make", {"id": "hit", "from": "hit_2", "tweak": "lower"})
        self.assertEqual(data["made"], ["hit_3"])
        code, data = self.post("/api/sfx/takes", {"id": "hit"})
        self.assertEqual([t["name"] for t in data["takes"]], ["hit_1", "hit_2", "hit_3"])
        self.assertEqual(data["takes"][2]["note"], "hit_2, lower")
        self.assertIsNone(data["current"])
        status, wav = self.get(data["takes"][0]["url"])
        self.assertEqual((status, wav[:4]), (200, b"RIFF"))

        code, data = self.post("/api/sfx/keep", {"id": "hit", "take": "hit_3"})
        self.assertEqual(code, 200, data)
        self.assertTrue((self.root / "assets" / "sfx" / "hit.wav").exists())
        self.assertEqual(sfxr.load(self.root / "sounds" / "hit.yaml"),
                         sfxr.load(self.root / "sounds" / "variants" / "hit_3.yaml"))
        self.assertEqual(manifest.load(self.root / "assets.yaml").assets[1].status, "draft")

        code, data = self.post("/api/sfx/make", {"id": "hit", "count": 1})  # like the current sound
        self.assertEqual(data["made"], ["hit_4"])
        self.assertEqual(self.post("/api/sfx/clear", {"id": "hit"})[1]["message"], "removed 4 takes")
        self.assertFalse((self.root / "sounds" / "variants").exists())
        self.assertEqual(self.post("/api/sfx/keep", {"id": "hit", "take": "../hit"})[0], 400)

    def test_import_sound_asks_before_replacing(self) -> None:
        self.post("/api/sfx/make", {"id": "hit", "preset": "blip", "count": 1})
        wav = (self.root / "sounds" / "variants" / "hit_1.wav").read_bytes()
        request = urllib.request.Request(self.base + "/api/upload?name=my%20sound.wav", data=wav,
                                         headers={"X-Gamekit": "1"})
        with urllib.request.urlopen(request) as response:
            upload = json.loads(response.read())["upload"]
        self.assertTrue(upload.endswith("my_sound.wav"))
        self.assertEqual(self.post("/api/sfx/import", {"id": "hit", "upload": upload})[0], 200)
        code, data = self.post("/api/sfx/import", {"id": "hit", "upload": upload})
        self.assertEqual((code, data["error"]), (400, "REPLACE?"))
        self.assertEqual(self.post("/api/sfx/import", {"id": "hit", "upload": upload, "force": True})[0], 200)
        self.assertEqual(self.post("/api/sfx/import", {"id": "hit", "upload": "../assets.yaml", "force": True})[0], 400)

    def test_draw_and_preview(self) -> None:
        art = self.root / "art"
        art.mkdir()
        rows = "\n".join(["kkkkkkkk"] * 16)
        frame = "    - |\n" + "\n".join("      " + r for r in rows.split("\n")[:16]) + "\n"
        (art / "hero.yaml").write_text("frames:\n  idle:\n" + frame * 2 + "  walk:\n" + frame * 4, encoding="utf-8")
        text = (self.root / "assets.yaml").read_text(encoding="utf-8").replace("size: [16, 16]", "size: [8, 16]")
        (self.root / "assets.yaml").write_text(text, encoding="utf-8")
        code, data = self.post("/api/art/draw", {"id": "hero"})
        self.assertEqual(code, 200, data)
        hero = json.loads(self.get("/api/state")[1])["assets"][0]
        self.assertEqual(hero["status"], "draft")
        code, png = self.get(hero["preview"])
        self.assertEqual((code, png[:4]), (200, b"\x89PNG"))


class BrowserTests(unittest.TestCase):
    def test_gamekit_browser_wins_and_bad_paths_fall_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "mybrowser.exe"
            fake.write_text("", encoding="utf-8")
            with unittest.mock.patch.dict("os.environ", {"GAMEKIT_BROWSER": str(fake)}):
                self.assertEqual(ui.find_browser(), str(fake))
            with unittest.mock.patch.dict("os.environ", {"GAMEKIT_BROWSER": str(Path(tmp) / "gone.exe")}), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertNotEqual(ui.find_browser(), str(Path(tmp) / "gone.exe"))


class LauncherTests(unittest.TestCase):
    def test_launcher_points_at_gamekit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bat = ui.write_launcher(Path(tmp) / "assets.yaml", Path("C:/tools/gamekit.py"))
            text = bat.read_bytes().decode("utf-8")
            self.assertEqual(bat.name, "Start Gamekit.bat")
            self.assertIn("gamekit.py\" -m \"assets.yaml\" ui", text)
            self.assertIn("\r\n", text)


if __name__ == "__main__":
    unittest.main()
