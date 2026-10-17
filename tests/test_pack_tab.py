"""The Packs tab: downloads waiting in packs/, importing them (.zip, folders, .rar/.7z), the shortlist, and taking a
boxed part of a pack image as a sprite or as a picture."""
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "gamekit" / "scripts"))

from PIL import Image  # noqa: E402

from gamekit_lib import manifest, packs, pictures, ui  # noqa: E402

RED, BLUE = (200, 30, 30), (20, 40, 200)
MANIFEST = """game: T
output: assets
palette: palette.hex
frame_files: true
assets:
  - {id: ship, kind: sprite, source: claude, status: todo, file: art/ship.png, size: [8, 8], frames: {idle: 2}}
  - id: rock
    kind: sprite
    source: pack
    status: draft
    file: art/rock.png
    size: [4, 4]
    license:
      name: CC-BY 4.0
      author: Someone
"""


def sheet() -> Image.Image:
    """16x8: a red 8x8 frame, then a blue one with a see-through 2 px border."""
    image = Image.new("RGBA", (16, 8), (0, 0, 0, 0))
    for x in range(8):
        for y in range(8):
            image.putpixel((x, y), (*RED, 255))
            if 1 < x < 6 and 1 < y < 6:
                image.putpixel((x + 8, y), (*BLUE, 255))
    return image


class PackTabTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "palette.hex").write_text("c81e1e r\n1428c8 b\n000000 k\n", encoding="utf-8")
        (self.root / "assets.yaml").write_text(MANIFEST, encoding="utf-8")
        self.packs = self.root / "packs"
        self.packs.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def loaded(self) -> manifest.Manifest:
        return manifest.load(self.root / "assets.yaml")

    def add_zip(self, name: str = "Space Ships.zip") -> Path:
        buffer = self.packs / name
        with zipfile.ZipFile(buffer, "w") as z:
            data = Path(self._tmp.name) / "s.png"
            sheet().save(data)
            z.write(data, "Space Ships/ships/sheet.png")
            z.writestr("Space Ships/License.txt", "License (Creative Commons Zero, CC0)")
            z.writestr("__MACOSX/Space Ships/._sheet.png", "junk")
        return buffer

    def licensed(self, name: str = "space-ships") -> packs.Pack:
        pack = packs.add(self.root, self.packs / "Space Ships.zip", name)
        pack.license = {"name": "CC0", "author": "Foozle", "url": ""}
        packs.save(pack)
        return pack

    # --- downloads and importing ---

    def test_downloads_lists_what_is_not_imported(self) -> None:
        self.add_zip()
        (self.packs / "Loose Folder").mkdir()
        (self.packs / "Loose Folder" / "a.png").write_bytes(b"x")
        (self.packs / "_extracted").mkdir()       # "_" folders are the user's own
        (self.packs / "notes.txt").write_text("x", encoding="utf-8")
        found = {d["name"]: d for d in packs.downloads(self.root)}
        self.assertEqual(set(found), {"Space Ships.zip", "Loose Folder"})
        self.assertEqual(found["Space Ships.zip"]["suggested"], "space-ships")
        self.assertEqual(found["Loose Folder"]["kind"], "folder")
        pack = packs.add(self.root, self.packs / "Space Ships.zip", "space-ships")
        self.assertEqual(pack.download, "Space Ships.zip")
        self.assertEqual({d["name"] for d in packs.downloads(self.root)}, {"Loose Folder"})
        self.assertEqual([p.as_posix() for p in packs.list_files(pack)], ["License.txt", "ships/sheet.png"])  # no __MACOSX

    def test_suggested_names_avoid_taken_ones(self) -> None:
        self.assertEqual(packs.suggest_name("Shoot`em Up.rar"), "shoot-em-up")
        self.assertEqual(packs.suggest_name("kenney_tanks.zip", {"kenney-tanks"}), "kenney-tanks-2")

    def test_a_pack_name_differing_only_in_case_is_refused(self) -> None:
        (self.packs / "Ships").mkdir()
        (self.packs / "Ships" / "a.png").write_bytes(b"x")
        with self.assertRaises(packs.PackError):
            packs.add(self.root, self.packs / "Ships", "ships")  # the same folder on Windows

    def test_7z_archives_are_unpacked_when_a_tool_is_there(self) -> None:
        tool = packs._unpacker()
        if tool is None:
            self.skipTest("no 7-Zip or Windows tar here")
        source = self.root / "src"
        (source / "Pack").mkdir(parents=True)
        sheet().save(source / "Pack" / "sheet.png")
        archive = self.packs / "pack.7z"
        if Path(tool).stem.lower().startswith("7z"):
            command = [tool, "a", str(archive), "Pack"]
        else:
            command = [tool, "--format", "7zip", "-cf", str(archive), "Pack"]
        if subprocess.run(command, cwd=source, capture_output=True).returncode != 0:
            self.skipTest("this tool can't write a .7z to test with")
        pack = packs.add(self.root, archive, "seven")
        self.assertEqual([p.as_posix() for p in packs.list_files(pack)], ["sheet.png"])
        self.assertEqual(pack.download, "pack.7z")

    # --- the shortlist and images ---

    def test_images_and_shortlist(self) -> None:
        self.add_zip()
        pack = packs.add(self.root, self.packs / "Space Ships.zip", "space-ships")
        self.assertEqual(packs.images(pack), [{"file": "ships/sheet.png", "width": 16, "height": 8}])
        packs.star(pack, "ships/sheet.png")
        self.assertEqual(packs.load(self.root, "space-ships").starred, ["ships/sheet.png"])
        packs.star(packs.load(self.root, "space-ships"), "ships/sheet.png", False)
        self.assertEqual(packs.load(self.root, "space-ships").starred, [])
        with self.assertRaises(packs.PackError):
            packs.star(pack, "../assets.yaml")

    # --- a boxed part as a sprite ---

    def test_a_box_the_sprite_size_is_used_pixel_for_pixel(self) -> None:
        self.add_zip()
        pack = self.licensed()
        part = packs.cut(pack, "ships/sheet.png", [8, 0, 8, 8])
        ship = next(a for a in self.loaded().assets if a.id == "ship")
        sprite = packs.to_sprite(self.loaded(), ship, part)
        self.assertEqual(sprite.size, (8, 8))
        self.assertEqual(sprite.getpixel((3, 3)), (*BLUE, 255))
        self.assertEqual(sprite.getpixel((0, 0))[3], 0)

    def test_another_size_is_fitted_with_the_whole_box(self) -> None:
        self.add_zip()
        pack = self.licensed()
        rock = next(a for a in self.loaded().assets if a.id == "rock")
        sprite = packs.to_sprite(self.loaded(), rock, packs.cut(pack, "ships/sheet.png", [8, 0, 8, 8]), snap=True)
        self.assertEqual(sprite.size, (4, 4))
        self.assertEqual(sprite.getpixel((0, 0))[3], 0)  # the see-through border counts: no zoom onto the subject
        self.assertEqual(sprite.getpixel((1, 1))[:3], (0x14, 0x28, 0xC8))  # snapped to the palette's blue
        with self.assertRaises(packs.PackError):
            packs.cut(pack, "ships/sheet.png", [10, 0, 8, 8])  # outside the image

    def test_use_writes_the_frame_and_the_manifest(self) -> None:
        self.add_zip()
        self.licensed()
        body = {"pack": "space-ships", "file": "ships/sheet.png", "box": [0, 0, 8, 8], "id": "ship", "frame": "ship_1"}
        ui.do_pack_use(self.loaded(), body)
        self.assertTrue((self.root / "assets" / "art" / "ship_1.png").exists())
        ship = next(a for a in self.loaded().assets if a.id == "ship")
        self.assertEqual((ship.source, ship.status, ship.license), ("pack", "draft", {"pack": "space-ships"}))
        self.assertIn("frames: {idle: 2}", (self.root / "assets.yaml").read_text(encoding="utf-8"))
        with self.assertRaises(ui.UserError):  # a file is there now: ask before replacing it
            ui.do_pack_use(self.loaded(), body)

    def test_use_needs_the_license(self) -> None:
        self.add_zip()
        packs.add(self.root, self.packs / "Space Ships.zip", "space-ships")
        with self.assertRaises(ui.UserError):
            ui.do_pack_use(self.loaded(), {"pack": "space-ships", "file": "ships/sheet.png", "id": "ship"})
        with self.assertRaises(ui.UserError):
            ui.do_pack_to_picture(self.loaded(), {"pack": "space-ships", "file": "ships/sheet.png"})

    # --- a boxed part as a picture ---

    def test_copy_to_pictures_and_using_it(self) -> None:
        self.add_zip()
        pack = self.licensed()
        path = packs.to_picture(self.loaded(), pack, "ships/sheet.png", [8, 0, 8, 8], "ship")
        with Image.open(path) as picture:
            self.assertEqual(picture.size, (1024, 1024))  # 8 px x 128, already a multiple of 16
            self.assertEqual(picture.getpixel((0, 0)), (255, 255, 255))  # white, not see-through: the AI reads colors
            self.assertEqual(picture.getpixel((512, 512)), BLUE)
        meta = pictures.read_meta(path)
        self.assertEqual((meta["pack"], meta["pack_file"], meta["box"], meta["for"]), ("space-ships", "ships/sheet.png", [8, 0, 8, 8], "ship"))
        wide = packs.to_picture(self.loaded(), pack, "ships/sheet.png", None)
        with Image.open(wide) as picture:
            self.assertEqual(picture.size, (1024, 512))
        # used from the Pictures tab, it is the pack's art: source pack, the pack's license
        ui.do_use_picture(self.loaded(), {"name": path.name, "id": "rock", "outline": False, "snap": False})
        rock = next(a for a in self.loaded().assets if a.id == "rock")
        self.assertEqual((rock.source, rock.license), ("pack", {"pack": "space-ships"}))
        self.assertNotIn("author: Someone", (self.root / "assets.yaml").read_text(encoding="utf-8"))
        self.assertEqual(manifest.validate(self.loaded(), check_files=False), [])

    def test_ai_pictures_remember_pack_art_they_came_from(self) -> None:
        self.add_zip()
        pack = self.licensed()
        pack.license["name"] = "CC-BY 4.0"
        packs.save(pack)
        copy = packs.to_picture(self.loaded(), pack, "ships/sheet.png", [0, 0, 8, 8])
        made = pictures.folder(self.loaded()) / "new-1.png"
        Image.new("RGB", (64, 64), RED).save(made)
        meta = pictures.record(made, {"prompt": "x", "refs": [str(copy)]}, {"seed": 1, "width": 64, "height": 64})
        self.assertEqual(meta["packs"], ["space-ships"])
        changes, note = ui._picture_source(self.loaded(), [made.name])
        self.assertEqual(changes, {"source": "ai"})
        self.assertIn("space-ships (CC-BY 4.0)", note)


class SetLicenseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "assets.yaml"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_flow_and_block_entries(self) -> None:
        self.path.write_text("assets:\n"
                             "  - {id: a, kind: icon, file: a.png, license: {name: CC0, author: X}}  # note\n"
                             "  - {id: b, kind: icon, file: b.png}\n"
                             "  - id: c\n    kind: icon\n    license:\n      name: CC0\n      author: Y\n    file: c.png\n",
                             encoding="utf-8")
        for asset_id in "abc":
            manifest.set_fields(self.path, asset_id, {"license": "{pack: my-pack}", "source": "pack"})
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("# note", text)
        assets = {a.id: a for a in manifest.load(self.path).assets}
        self.assertEqual({k: (a.license, a.source, a.file) for k, a in assets.items()},
                         {k: ({"pack": "my-pack"}, "pack", f"{k}.png") for k in "abc"})
        with self.assertRaises(manifest.ManifestError):
            manifest.set_fields(self.path, "a", {"source": "{pack: x}"})  # only license takes a {pack: ...}


if __name__ == "__main__":
    unittest.main()
