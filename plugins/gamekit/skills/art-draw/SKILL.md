---
name: art-draw
description: Draw pixel art sprites, icons, tiles and UI images as text rows (one character per pixel) on the game's palette, render them to PNG sprite sheets, and review them visually. Use when the user asks Claude to draw, redraw, animate or touch up a pixel art asset listed in assets.yaml (source claude).
---

# Draw pixel art as text

Claude draws an asset as a YAML text sprite, renders it to PNG with the gamekit CLI, then looks at
an enlarged preview and fixes what's off. The text file is the source; the PNG is generated.

CLI (run from the game's root, the folder with `assets.yaml`; `python3` if `python` isn't found;
needs PyYAML and Pillow from `${CLAUDE_PLUGIN_ROOT}/requirements.txt`, ask before installing):

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" draw <id>        # art/<id>.yaml -> PNG (+ .json for animations)
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" preview <id> --scale 8 -o preview.png
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" check <id>
```

If `assets.yaml` sets `frame_files: true`, animated sprites are written as one PNG per frame (`<name>.png` = idle frame 0, `<name>_1.png`, `<name>_walk_1.png`, `<name>_attack.png`...) instead of a sheet + `.json`; `check` and `preview` handle both.

## Text sprite format (`art/<id>.yaml`, or the asset's `src`)

```yaml
# Still image: one block of rows.
rows: |
  ..kkkk..
  .kwwwwk.
# Animated: name -> list of frames (use instead of rows). Sheet = one row per animation.
frames:
  idle:
    - |
      ..kkkk..
  walk:
    - |
      ...
keys:          # optional; char -> palette color name, palette index, or RRGGBB
  a: 0d0b12
```

- `.` is transparent. Every other character must be a key.
- Without `keys`, the palette's one-character color names are the keys (see `palette.hex`:
  `RRGGBB name` per line). Prefer palette colors; `check` flags anything off-palette.
- Every row and every frame of an asset must be the same size, and match the manifest `size`.
  Frame counts per animation must match the manifest `frames`.

## Steps

1. Read the asset's manifest entry (size, frames, notes) and the palette file. If the game already
   has art for it (`replaces`), look at that first to keep the established style and silhouette.
   If `assets.yaml` sets `code_art`, the game's current drawing of the sprite is the entry of that name
   (`replaces`, else the id; frames `<name>_walk_1`...) in that file: start from it.
2. Write `art/<id>.yaml`. Pixel art basics at small sizes:
   - Dark 1px outline around the silhouette; readable shape first, details second.
   - Light from the top-left: 1 highlight and 1-2 shade colors per material, no gradients.
   - Keep the palette small per sprite (4-8 colors). Avoid stray single pixels and "pillow shading".
   - Animation: change as few pixels as needed; keep the outline and feet consistent so it doesn't
     jitter. Walk cycles: contact, pass, contact, pass (mirror the legs).
3. Run `draw <id>`. Fix every reported problem (sizes, frames, unknown keys).
4. Run `preview <id> --scale 8 -o preview.png` and **look at the image** (Read it). Judge it at
   game scale too (`--scale 2`). Fix and redraw until it reads well; say what you changed.
5. Set the asset's `status: draft` in `assets.yaml` (`done` only when the user approves), then
   show the user the preview. Delete `preview.png` when finished unless they want it.
