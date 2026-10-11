---
name: art-export
description: Export the user's Aseprite (.aseprite) files to PNG sprite sheets with the Aseprite command line, and check any finished image (exported, downloaded or drawn) against the manifest size, animation frames and palette. Use after the user draws or edits art in Aseprite, adds downloaded images, or asks whether the art is consistent.
---

# Export Aseprite files and check images

CLI (run from the game's root; `python3` if `python` isn't found; needs PyYAML and Pillow from
`${CLAUDE_PLUGIN_ROOT}/requirements.txt`, ask before installing):

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" export [ids...]   # art/<id>.aseprite -> PNG sheet + .json
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" check [ids...]    # size, frames, palette
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" preview [ids...] --scale 4 -o preview.png
```

`export` with no ids exports every `source: self` asset whose `.aseprite` file exists.
It never edits `.aseprite` files; they are the user's work.

## Aseprite setup

- Aseprite runs on the user's own computer. In a cloud session it's not installed: say so and
  stop rather than trying to install it.
- The CLI looks for `$GAMEKIT_ASEPRITE`, then `aseprite` on PATH, then the usual Windows / Steam /
  macOS install folders. If it isn't found, ask the user where `Aseprite.exe` is and run with
  `GAMEKIT_ASEPRITE` set to that path.

## How the user should set up a file

- Canvas = one frame at the manifest `size`.
- One **tag** per animation, named like the manifest `frames` keys (`idle`, `walk`...). Each tag
  becomes one row of the sheet. A file with no tags exports as one animation, `default`, or as a
  still image if it has one frame.
- Use the game's palette (Aseprite: load `palette.hex` / `.gpl` into the palette panel).

## After exporting or adding images

1. Run `check`. Explain each problem in plain words and how to fix it in Aseprite
   (e.g. "frame size 32x32 but the manifest says 16x16: Sprite > Canvas Size").
   Off-palette colors from packs can be fine if the user accepts them; ask.
2. Run `preview` and look at the image (Read it) to catch visual issues the checks can't.
3. Update `status` in `assets.yaml` (`draft` -> `done` once the user is happy).
