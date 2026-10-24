---
name: art-draw
description: Draw pixel art sprites, icons, tiles and UI images as text rows (one character per pixel) on the game's palette, in batches started from the game's own code art, and review them visually as drafts the user puts into the game. Use when the user asks Claude to draw, redraw, animate or touch up a pixel art asset listed in assets.yaml (source claude), and touching up or animating drafts made from AI pictures or sprites ("touch up the shambler drafts", "animate the ghoul drafts", kept in pictures/).
---

# Draw pixel art as text

Claude draws an asset as a YAML text sprite, renders it to PNG with the gamekit CLI, then looks at
an enlarged preview and fixes what's off. The text file is the source; the PNG is generated.

CLI (run from the game's root, the folder with `assets.yaml`; `python3` if `python` isn't found;
needs PyYAML and Pillow from `${CLAUDE_PLUGIN_ROOT}/requirements.txt`, ask before installing):

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" seed <ids> | --kind icon [--status todo]   # art/<id>.yaml from the game's code art
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" preview <ids> --draft --scale 8 -o preview.png  # drafts, drawn in memory only
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" preview <ids> --compare --scale 8 -o preview.png  # now | draft, side by side
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" draw <ids>       # art/<id>.yaml -> the game's PNG (only when the user says so)
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" check <id>
```

`preview` also takes `--kind` / `--status` (one sheet for a whole family), `--bg checker|<floor name>|RRGGBB`
(default: the first of `sprites.floors`, the color the game shows sprites on) and `--columns`.

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

## Touching up an AI draft

"Touch up the <id> drafts" (or "animate the <id> drafts") means drafts made from AI pictures or sprites, kept in `pictures/` (not in the game): the
asset page's **Touch up with Claude** (or `gamekit.py touchup <id> <frame>=<picture> ... [--every-frame]`) saved
each as `pictures/<name>-touchup-<w>x<h>.png` with its pixels as text rows beside it (same name, `.yaml`) and a
`.json` (`for`: the asset, `frame`, `sprite_of`: the full-size picture, `copy_of`: the frame it was copied
from). Find them with Glob `pictures/*-touchup-*.yaml` and their `.json` `for`; take the newest per frame.
**Don't touch the asset's own files, `art/<id>.yaml` or `assets.yaml`**: the user puts a draft in the game
with **Use** when they like it.

1. Read each yaml, then look at its PNG (zoomed with `preview`) and the full-size picture it came from (follow
   `sprite_of` / `cutout_of` in the `.json` files until a picture has neither): it shows what the creature is
   meant to look like.
2. Fix what shrinking breaks, keeping the draft's colors and overall shape: center the creature and make it
   left-right symmetric if the game wants that; a clean 1 px outline (no gaps, no doubled corners); a readable
   face (eyes as clear 1-2 px marks in their bright color, not touching the outline); remove stray pixels and
   noise; a strong silhouette.
3. Animation drafts (the Animate panel's **Animate with Claude** / **Touch up with Claude**): frames without a picture
   are copies of the frame before them (`copy_of` in their `.json`). Make each one move
   (walk: legs alternate, body bobs 1 px; attack: lean or reach), changing as few pixels as possible and keeping
   the outline and feet steady.
4. Edit the yaml in place (keep its first comment line), draw its PNG again with
   `gamekit.py touchup-render <name>.yaml`, look at it again, and say what changed. The tile on the Pictures tab
   updates; tell the user to press **Use** on it to put it in the game.

## Steps

Only the user puts art into the game: Claude writes and reviews **drafts** (`art/<id>.yaml`, which the game
doesn't read), and the user presses **Use draft** on the asset page's Art tab (or asks Claude to run `draw`).
Work in batches of related assets (8-12 icons of one family, an icon and its `_lg` twin, one creature's frames).

1. Read the batch's manifest entries (size, frames, notes) and the palette file. Find out what each asset
   is for: its `notes`, the game's art brief, and the game data that uses it (an upgrade's description...).
   If `notes` is empty, add a short one in `assets.yaml` so the next session doesn't search again.
2. Start each draft:
   - If `assets.yaml` sets `code_art`, run `seed <ids>` (or `seed --kind icon --status todo`): it writes
     `art/<id>.yaml` holding the game's current drawing, pixel for pixel, with frames named the way the
     manifest expects. It never overwrites a yaml that exists. Redesign from there, keeping what works.
   - Otherwise write `art/<id>.yaml` from scratch. If the game has art for it (`replaces`), look at that first
     to keep the established style and silhouette. A reference picture helps for new designs: the
     `picture-make` skill makes one on the user's PC, then draw the sprite from it rather than shrinking it.
3. Redesign each yaml. Pixel art basics at small sizes:
   - Dark 1px outline around the silhouette; readable shape first, details second. If `assets.yaml` has a
     `sprites:` block, use its `outline` color and never its `reserved_colors`.
   - Light from the top-left: 1 highlight and 1-2 shade colors per material, no gradients.
   - Keep the palette small per sprite (4-8 colors). Avoid stray single pixels and "pillow shading".
   - Animation: change as few pixels as needed; keep the outline and feet consistent so it doesn't
     jitter. Walk cycles: contact, pass, contact, pass (mirror the legs).
   - Icons in a family should read as a set: same outline, light direction and visual weight.
4. Run `preview <ids> --compare --scale 8 -o preview.png` and **look at the image** (Read it): what the game
   shows now next to each draft, on the game's floor color. Judge small ones at game scale too
   (`--scale 3`). It reports yaml mistakes (sizes, frames, unknown keys); fix them. Repeat until each draft
   clearly reads better than now; if one doesn't, say so (the user may prefer to keep the game's version).
5. Tell the user what changed per asset and that the drafts are waiting on the Art tab (**Only Claude's drafts
   waiting for you**, then **Use draft** or **Use all drafts shown**). Using one moves it from todo to draft;
   `done` only when the user approves; `keep` when they decide the game's own version stays.
   Run `draw <ids>` yourself only when the user asks you to put them in the game. Delete `preview.png`.
