import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "gamekit" / "scripts"))

from gamekit_lib import credits, manifest, ui  # noqa: E402

TEMPLATE = Path(__file__).resolve().parent.parent / "plugins" / "gamekit" / "templates" / "assets.yaml"


def write_manifest(folder: Path, body: str) -> Path:
    path = folder / "assets.yaml"
    path.write_text("game: Test\noutput: assets\nassets:\n" + body, encoding="utf-8")
    return path


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def problems(self, body: str, check_files: bool = False) -> list[str]:
        return manifest.validate(manifest.load(write_manifest(self.folder, body)), check_files)

    def test_template_is_valid(self) -> None:
        loaded = manifest.load(TEMPLATE)
        self.assertEqual(manifest.validate(loaded, check_files=False), [])

    def test_valid_sprite_and_sfx(self) -> None:
        body = (
            "  - {id: hero, kind: sprite, source: claude, file: sprites/hero.png, size: [16, 16],"
            " frames: {walk: 4}}\n"
            "  - {id: hit, kind: sfx, source: sfxr, file: sfx/hit.wav}\n"
        )
        self.assertEqual(self.problems(body), [])

    def test_duplicate_and_bad_ids(self) -> None:
        body = (
            "  - {id: hero, kind: icon, source: self, file: a.png, size: [8, 8]}\n"
            "  - {id: hero, kind: icon, source: self, file: b.png, size: [8, 8]}\n"
            "  - {id: Bad-Id, kind: icon, source: self, file: c.png, size: [8, 8]}\n"
        )
        problems = self.problems(body)
        self.assertTrue(any("duplicate id" in p for p in problems))
        self.assertTrue(any("snake_case" in p for p in problems))

    def test_wrong_extension_and_missing_size(self) -> None:
        problems = self.problems("  - {id: boom, kind: sfx, source: sfxr, file: sfx/boom.ogg}\n"
                                 "  - {id: tree, kind: sprite, source: pack, file: tree.png}\n")
        self.assertTrue(any("must end in .wav" in p for p in problems))
        self.assertTrue(any("size must be" in p for p in problems))

    def test_audio_has_no_size_and_only_sprites_have_frames(self) -> None:
        problems = self.problems(
            "  - {id: song, kind: music, source: synth, file: m.ogg, size: [1, 1]}\n"
            "  - {id: tile, kind: tileset, source: self, file: t.png, size: [16, 16], frames: {a: 2}}\n")
        self.assertTrue(any("has no pixel size" in p for p in problems))
        self.assertTrue(any("only sprites" in p for p in problems))

    def test_license_needed_once_not_todo(self) -> None:
        todo = "  - {id: tree, kind: sprite, source: pack, status: todo, file: t.png, size: [16, 16]}\n"
        self.assertEqual(self.problems(todo), [])
        draft = todo.replace("todo", "draft")
        problems = self.problems(draft)
        self.assertTrue(any("license.name" in p for p in problems))
        self.assertTrue(any("license.author" in p for p in problems))

    def test_done_asset_needs_its_file(self) -> None:
        body = "  - {id: hit, kind: sfx, source: sfxr, status: done, file: sfx/hit.wav}\n"
        self.assertTrue(any("missing" in p for p in self.problems(body, check_files=True)))
        (self.folder / "assets" / "sfx").mkdir(parents=True)
        (self.folder / "assets" / "sfx" / "hit.wav").write_bytes(b"")
        self.assertEqual(self.problems(body, check_files=True), [])

    def test_summary_counts_frames(self) -> None:
        loaded = manifest.load(write_manifest(self.folder, (
            "  - {id: a, kind: sprite, source: claude, status: done, file: a.png, size: [8, 8],"
            " frames: {idle: 2, walk: 4}}\n"
            "  - {id: b, kind: sprite, source: claude, file: b.png, size: [8, 8]}\n"
            "  - {id: c, kind: sfx, source: sfxr, file: c.wav}\n")))
        table = manifest.summary(loaded)
        self.assertEqual(table["sprite"]["done"], 1)
        self.assertEqual(table["sprite"]["todo"], 1)
        self.assertEqual(table["sprite"]["frames"], 7)
        self.assertEqual(table["sfx"]["frames"], 0)

    def test_credits_lists_authors_and_skips_todo(self) -> None:
        loaded = manifest.load(write_manifest(self.folder, (
            "  - {id: tree, kind: sprite, source: pack, status: done, file: t.png, size: [16, 16],"
            " license: {name: CC-BY 4.0, author: Ada, url: 'https://example.com'}}\n"
            "  - {id: hero, kind: sprite, source: claude, status: draft, file: h.png, size: [16, 16]}\n"
            "  - {id: rock, kind: sprite, source: pack, status: todo, file: r.png, size: [16, 16]}\n")))
        text = credits.render(loaded)
        self.assertIn("**Ada**, CC-BY 4.0 ([source](https://example.com)): tree", text)
        self.assertIn("1 asset drawn by Claude", text)
        self.assertNotIn("rock", text)



class BadValueTests(unittest.TestCase):
    """Mistakes in assets.yaml load and get explained by validate, instead of crashing every tool."""

    def test_bad_values_load_and_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / "assets.yaml"
            path.write_text(
                "game: T\nframe_files: \"true\"\nframe_file: true\n"
                "audio: {sfx_peak_db: \"-3 dB\"}\nsprites: {reserved_colors: \"#FF00FF\"}\nassets:\n"
                "  - {id: hero, kind: sprite, source: pack, status: draft, file: hero.png, size: [8, 8],"
                " frames: {idle: \"2\"}, license: CC0, src: /abs/hero.aseprite, licence: CC0}\n",
                encoding="utf-8")
            loaded = manifest.load(path)
            self.assertEqual(loaded.sfx_peak_db, -1.0)
            self.assertEqual(loaded.reserved_colors, [])
            self.assertEqual(loaded.assets[0].frame_count(), 0)
            problems = "\n".join(manifest.validate(loaded, check_files=False))
            for expected in ("unknown setting 'frame_file'", "frame_files: true or false", "audio.sfx_peak_db",
                             "sprites.reserved_colors", "unknown keys licence", "license must be",
                             "src must be a path inside", "frames must map"):
                self.assertIn(expected, problems)
            self.assertIn("problems", ui.state(loaded))  # the page loads and can show them

    def test_font_may_give_a_glyph_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_manifest(Path(tmp), "  - {id: font, kind: font, source: claude, file: f.png, size: [5, 7]}\n"
                                             "  - {id: font2, kind: font, source: claude, file: f.ttf}\n")
            self.assertEqual(manifest.validate(manifest.load(path), check_files=False), [])


class SetFieldsTests(unittest.TestCase):
    def test_notes_mentioning_an_id_are_left_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_manifest(Path(tmp),
                                  "  - {id: bat_swarm, kind: sprite, source: claude, file: s.png, size: [8, 8],"
                                  " notes: 'many of id: bat, flying together'}\n"
                                  "  - {id: bat, kind: sprite, source: claude, file: b.png, size: [8, 8]}\n")
            manifest.set_fields(path, "bat", {"source": "ai"})
            sources = {a.id: a.source for a in manifest.load(path).assets}
            self.assertEqual(sources, {"bat_swarm": "claude", "bat": "ai"})

    def test_refuses_a_change_that_would_touch_another_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # the only status: text is inside the notes, before any real status key
            path = write_manifest(Path(tmp), "  - {id: bat, kind: sprite, notes: 'status: odd', source: claude,"
                                             " file: b.png, size: [8, 8]}\n")
            before = path.read_text(encoding="utf-8")
            with self.assertRaises(manifest.ManifestError):
                manifest.set_fields(path, "bat", {"status": "draft"})
            self.assertEqual(path.read_text(encoding="utf-8"), before)

if __name__ == "__main__":
    unittest.main()
