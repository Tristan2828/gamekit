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

from PIL import Image, ImageDraw  # noqa: E402

from gamekit_lib import engines, manifest, pictures, ui  # noqa: E402

TEMPLATES = Path(__file__).resolve().parent.parent / "plugins" / "gamekit" / "templates"

# Plays the picture model: same protocol, draws a red square on white instead of painting.
FAKE_WORKER = textwrap.dedent('''
    import json, sys
    from PIL import Image, ImageDraw
    def reply(o):
        sys.stdout.write("@@" + json.dumps(o) + "\\n"); sys.stdout.flush()
    print("noise that isn't a reply")
    reply({"step": "Loading the picture model"})
    reply({"ready": True})
    for line in sys.stdin:
        r = json.loads(line)
        if r["prompt"] == "fail":
            reply({"ok": False, "error": "could not paint"}); continue
        reply({"step": "Painting: step 1 of 1"})
        image = Image.new("RGB", (r["width"], r["height"]), "white")
        ImageDraw.Draw(image).rectangle([r["width"] // 4, r["height"] // 4, r["width"] * 3 // 4 - 1, r["height"] - 1], fill=(200, 30, 30))
        image.save(r["out"])
        reply({"ok": True, "seed": r["seed"], "width": r["width"], "height": r["height"]})
''')

MANIFEST = """game: T
palette: palette.hex
assets:
  - {id: blob, kind: sprite, source: claude, status: todo, file: art/blob.png, size: [8, 8]}  # keep me
  - id: walker
    kind: sprite
    source: claude
    file: art/walker.png
    size: [8, 8]
    frames: {idle: 1, walk: 2}
  - {id: floor, kind: tileset, source: claude, file: art/floor.png, size: [16, 16]}
"""


class FakeWorkerMixin:
    def fake_worker(self, folder: Path) -> engines.Worker:
        script = folder / "fake_worker.py"
        script.write_text(FAKE_WORKER, encoding="utf-8")
        return engines.Worker(engines.get("picture"), [sys.executable, "-u", str(script)])


class WorkerTests(FakeWorkerMixin, unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        self.env = unittest.mock.patch.dict("os.environ", {"GAMEKIT_ENGINES": str(self.folder / "engines")})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self._tmp.cleanup()

    def test_protocol_steps_and_errors(self) -> None:
        w = self.fake_worker(self.folder)
        steps: list[str] = []
        answer = w.ask({"prompt": "a", "out": str(self.folder / "a.png"), "width": 64, "height": 64, "seed": 5},
                       steps.append)
        self.assertEqual(answer["seed"], 5)
        self.assertEqual(steps, ["Starting the pictures model", "Loading the picture model", "Painting: step 1 of 1"])
        self.assertTrue((self.folder / "a.png").exists())
        with self.assertRaisesRegex(engines.EngineError, "could not paint"):
            w.ask({"prompt": "fail"})
        self.assertTrue(w.running())  # one failed picture doesn't stop the model
        w.stop()
        self.assertFalse(w.running())

    def test_a_crashed_worker_is_reported(self) -> None:
        script = self.folder / "crash.py"
        script.write_text("import sys; sys.exit(3)", encoding="utf-8")
        w = engines.Worker(engines.get("picture"), [sys.executable, str(script)])
        with self.assertRaisesRegex(engines.EngineError, "exit code 3"):
            w.start()

    def test_not_set_up(self) -> None:
        with self.assertRaisesRegex(engines.EngineError, "isn't set up"):
            engines.Worker(engines.get("picture")).start()

    def test_places_and_torch_choice(self) -> None:
        self.assertEqual(engines.home(), self.folder / "engines")
        self.assertFalse(engines.is_installed(engines.get("picture")))
        with unittest.mock.patch.dict("os.environ", {"GAMEKIT_TORCH": "cuda"}):
            self.assertEqual(engines.graphics(), "cuda")
        cuda = engines.torch_commands("uv", "py", "cuda")
        self.assertIn(engines.CUDA_INDEX, cuda[0])
        cpu = engines.torch_commands("uv", "py", "cpu")
        self.assertEqual(cpu[0][-3:], ["torch", "torchvision", "torchaudio"])
        if sys.platform == "win32":
            rocm = engines.torch_commands("uv", "py", "rocm")
            self.assertTrue(any("rocm7.2.1" in part for part in rocm[1]))
        with self.assertRaises(engines.EngineError):
            engines.get("nope")


class PictureFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "assets.yaml").write_text(MANIFEST, encoding="utf-8")
        shutil.copyfile(TEMPLATES / "palette.hex", self.root / "palette.hex")
        self.m = manifest.load(self.root / "assets.yaml")
        self.by_id = {a.id: a for a in self.m.assets}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def picture(self, name: str = "red-1.png", background: str = "white") -> str:
        folder = pictures.folder(self.m)
        folder.mkdir(exist_ok=True)
        image = Image.new("RGB", (200, 100), background)
        ImageDraw.Draw(image).rectangle([80, 20, 119, 99], fill=(200, 30, 30))
        image.save(folder / name)
        pictures.record(folder / name, {"prompt": "red block", "steps": 4}, {"seed": 1, "width": 200, "height": 100})
        return name

    def test_names_list_keep_remove(self) -> None:
        self.assertEqual(pictures.slug("A Bat!! with   RED eyes"), "a-bat-with-red-eyes")
        self.assertEqual(pictures.new_path(self.m, "a bat", 7).name, "a-bat-7.png")
        name = self.picture("a-bat-7.png")
        self.assertEqual(pictures.new_path(self.m, "a bat", 7).name, "a-bat-7-2.png")
        listed = pictures.list_all(self.m)
        self.assertEqual([p["name"] for p in listed], [name])
        self.assertEqual(listed[0]["meta"]["prompt"], "red block")
        pictures.keep(self.m, name)
        self.assertTrue(pictures.read_meta(pictures.folder(self.m) / name)["kept"])
        pictures.remove(self.m, name)
        self.assertEqual(pictures.list_all(self.m), [])
        self.assertTrue((pictures.folder(self.m) / "_removed" / name).exists())
        for bad in ("../assets.yaml", "x/y.png", "nope.png", "a.txt"):
            with self.assertRaises(pictures.PictureError):
                pictures.path_of(self.m, bad)

    def test_to_sprite(self) -> None:
        image = Image.new("RGB", (200, 100), "white")
        ImageDraw.Draw(image).rectangle([80, 20, 119, 99], fill=(200, 30, 30))  # 40 x 80, touching the bottom
        sprite = pictures.to_sprite(image, (8, 8))
        self.assertEqual(sprite.size, (8, 8))
        alphas = {sprite.getpixel((x, y))[3] for x in range(8) for y in range(8)}
        self.assertEqual(alphas, {0, 255})                       # hard edges only
        self.assertEqual(sprite.getpixel((4, 7))[:3], (200, 30, 30))  # standing on the bottom row
        self.assertEqual(sprite.getpixel((0, 0))[3], 0)          # background gone
        self.assertEqual(sprite.getpixel((4, 0))[3], 255)        # 40x80 fits 4x8: full height
        with self.assertRaises(pictures.PictureError):
            pictures.to_sprite(Image.new("RGB", (50, 50), "white"), (8, 8))

    def test_use_as_asset(self) -> None:
        name = self.picture()
        problems = pictures.use_as_asset(self.m, self.by_id["blob"], name)
        self.assertEqual(problems, [])  # right size, every color on the palette
        with Image.open(self.root / "assets" / "art" / "blob.png") as made:
            self.assertEqual(made.size, (8, 8))
        with self.assertRaisesRegex(pictures.PictureError, "animated"):
            pictures.use_as_asset(self.m, self.by_id["walker"], name)
        pictures.use_as_asset(self.m, self.by_id["floor"], name)  # a tile fills its whole size
        with Image.open(self.root / "assets" / "art" / "floor.png") as tile:
            self.assertEqual((tile.size, tile.getpixel((0, 0))[3]), ((16, 16), 255))


class SetFieldsTests(unittest.TestCase):
    def test_flow_and_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "assets.yaml"
            path.write_text(MANIFEST, encoding="utf-8")
            manifest.set_fields(path, "blob", {"source": "ai", "status": "draft"})
            manifest.set_fields(path, "walker", {"source": "ai", "status": "done"})  # walker had no status
            text = path.read_text(encoding="utf-8")
            self.assertIn("{id: blob, kind: sprite, source: ai, status: draft,", text)
            self.assertIn("# keep me", text)
            got = {a.id: (a.source, a.status) for a in manifest.load(path).assets}
            self.assertEqual(got, {"blob": ("ai", "draft"), "walker": ("ai", "done"), "floor": ("claude", "todo")})
            with self.assertRaises(manifest.ManifestError):
                manifest.set_fields(path, "blob", {"source": "a i: x"})
            self.assertEqual(manifest.validate(manifest.load(path), check_files=False), [])


class PicturePageTests(FakeWorkerMixin, unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "assets.yaml").write_text(MANIFEST, encoding="utf-8")
        shutil.copyfile(TEMPLATES / "palette.hex", self.root / "palette.hex")
        fake = self.fake_worker(self.root)
        self.patches = [unittest.mock.patch.dict("os.environ", {"GAMEKIT_ENGINES": str(self.root / "engines")}),
                        unittest.mock.patch.object(engines, "worker", lambda name: fake),
                        unittest.mock.patch.object(engines, "is_installed", lambda engine: True),
                        unittest.mock.patch.object(engines, "stop_all", fake.stop)]
        for p in self.patches:
            p.start()
        self.fake = fake
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

    def wait_for_job(self) -> dict:
        for _ in range(200):
            job = self.post("/api/job", {})[1]["job"]
            if job and job["state"] != "running":
                return job
            time.sleep(0.05)
        self.fail("the job never finished")

    def test_make_then_use(self) -> None:
        self.assertEqual(self.post("/api/pictures/make", {"prompt": ""})[0], 400)
        code, _ = self.post("/api/pictures/make", {"prompt": "a red block", "takes": 2, "width": 256, "height": 256, "seed": 9})
        self.assertEqual(code, 200)
        job = self.wait_for_job()
        self.assertEqual(job["state"], "done", job)
        self.assertEqual(job["result"]["made"], ["a-red-block-9.png", "a-red-block-10.png"])
        listed = self.post("/api/pictures", {})[1]["pictures"]
        self.assertEqual({p["name"] for p in listed}, {"a-red-block-9.png", "a-red-block-10.png"})
        self.assertEqual(listed[0]["meta"]["width"], 256)

        code, data = self.post("/api/pictures/use", {"name": "a-red-block-9.png", "id": "blob"})
        self.assertEqual(code, 200, data)
        blob = manifest.load(self.root / "assets.yaml").assets[0]
        self.assertEqual((blob.source, blob.status), ("ai", "draft"))
        code, data = self.post("/api/pictures/use", {"name": "a-red-block-9.png", "id": "blob"})
        self.assertEqual((code, data["error"]), (400, "REPLACE?"))

    def test_errors_and_one_job_at_a_time(self) -> None:
        self.post("/api/pictures/make", {"prompt": "fail"})
        job = self.wait_for_job()
        self.assertEqual((job["state"], job["error"]), ("error", "could not paint"))
        ui.CURRENT["job"] = ui.Job("something long")  # still running
        code, data = self.post("/api/pictures/make", {"prompt": "a red block"})
        self.assertEqual((code, data["error"]), (400, "still busy: something long"))


if __name__ == "__main__":
    unittest.main()
