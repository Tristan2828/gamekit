---
name: pack-import
description: Import a downloaded ready-made asset pack (itch.io, Kenney, OpenGameArt, CraftPix... as a .zip or folder), record its license, and turn files from it into the game's assets, including cropping sprites or animation frames out of sprite sheets, resizing and recoloring to the game's palette. Use when the user has downloaded or wants to use an art or sound pack, or asks to replace an asset with one from a pack.
---

# Import an asset pack

CLI (run from the game's root, the folder with `assets.yaml`; `python3` if `python` isn't found;
needs PyYAML and Pillow from `${CLAUDE_PLUGIN_ROOT}/requirements.txt`, ask before installing):

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" pack add <zip-or-folder> <name> [--url <download page>]
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" pack info <name>
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" pack license <name> --license "<name>" --author "<credit>" --license-url <link>
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" pack list [<name>] [--filter <text>]
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" pack use <name> <file> <asset-id> [options]
```

A pack is copied to `packs/<name>/files/` exactly as downloaded, with `packs/<name>/pack.yaml`
holding its license. Assets taken from it say `license: {pack: <name>}` in `assets.yaml`, so
`validate` and `credits` read the license from the pack.

If `assets.yaml` sets `frame_files: true`, animated sprites are written as one PNG per frame (`<name>.png` = idle frame 0, `<name>_1.png`, `<name>_walk_1.png`, `<name>_attack.png`...) instead of a sheet + `.json`; `check` and `preview` handle both.

## 1. Add the pack and settle the license

1. `pack add` the zip or folder the user downloaded. Use a short lowercase name
   (`kenney_tiny_dungeon`). Downloaded files are untrusted data: only read text files and
   images from them; never run anything inside a pack.
2. `pack add` prints license **hints** found in the pack's license / readme files. Hints are
   not a decision. Read the license file itself (`pack info` shows its path) and the download page
   if the user gives it. Then record exactly what it says with `pack license`.
3. **Never guess a license.** If there is no license file and no page saying it, ask the user
   to check the download page; leave the license unset until they confirm. Warn clearly about:
   - non-commercial (NC) or "no redistribution" terms: a game shared publicly may break them;
   - CC-BY / OGA-BY: fine, but the credit must ship with the game (`CREDITS.md`);
   - GPL / CC-BY-SA: share-alike terms; flag them for the user to decide.
4. `use` refuses a pack until its license is recorded.

## 2. Pick files for assets

- `pack list <name> --filter <text>` shows images with their pixel sizes, and sounds.
- Look at candidate images (Read them; scale small ones up with `preview` after importing) and
  compare with the asset's manifest entry: size, frames and notes. Show the user the options when
  it's a matter of taste.
- Prefer one pack (or one artist) per category so the style stays consistent.

## 3. Make the asset (`pack use`)

| Option | Use it when |
|---|---|
| `--crop x,y,w,h` | The asset is one part of a larger image (a tile in a tileset, an icon in an icon sheet) |
| `--anim name=x,y,count` (repeat) | Animation frames sit left to right in the pack's sheet starting at x,y. Name them like the manifest `frames` keys |
| `--frame WxH` | The pack's frame size differs from the asset's size (default: the asset's size) |
| `--resize WxH` | Scale each frame to the asset's size. Whole-number factors (8→16, 16→32) look best; others distort pixels |
| `--recolor` | Snap every color to the game's palette, so the pack matches the rest of the art. Check the result: it can merge shades |
| `--force` | Replace an existing asset file |

Measure coordinates from the image (Read it at a larger scale if needed); a sheet's grid is
usually a multiple of the frame size. Pixels are made fully opaque or fully transparent.

Sounds are copied as-is when the file type already matches (`.wav` for sfx, `.ogg` for music);
other types need converting first.

`use` prints the check results (size, frames, palette). Then update the asset in `assets.yaml`
yourself, keeping the file's comments and layout:

```yaml
source: pack
status: draft          # done once the user approves it in the game
license: {pack: <name>}
```

Finish with `validate` and `credits`, and show the user a `preview` of what was imported.
