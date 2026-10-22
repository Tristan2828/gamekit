---
name: assets-plan
description: Build or extend a game's asset manifest (assets.yaml) by surveying the game's code, data and design docs for every sprite, tileset, icon, UI image, sound effect and music track it needs. Use when the user wants to know how many assets a game needs, start an asset list, plan an art or audio pass, or add newly designed content to the list.
---

# Plan a game's assets

The goal is an `assets.yaml` at the game's root that lists **every** asset the game needs, with
enough detail (size, frames, source) that each one can be made or found without re-reading the code.

## Tools

The CLI ships with this plugin. Run it from the game's root folder:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" <command>
```

Use `python3` if `python` isn't found. It needs PyYAML; if the import fails, run
`python -m pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"` (ask the user first).

| Command | Does |
|---|---|
| `init --game "<name>"` | Creates `assets.yaml` and a starter `palette.hex` if missing (never overwrites) |
| `validate` | Checks ids, kinds, file extensions, sizes, frames and licenses |
| `status --todo` | Counts per kind and status, and lists what's unfinished |

The field reference is the comment block at the top of `assets.yaml` (from
`${CLAUDE_PLUGIN_ROOT}/templates/assets.yaml`). Read it before writing entries.

## Steps

1. **Start or load the manifest.** Run `init` if there's no `assets.yaml`. If one exists, read it:
   you are extending it, so keep existing entries, ids and statuses unless the user says otherwise.
   Delete the template's example entries (`hero`, `hit`) when adding real ones.
2. **Survey the game.** Find everything that is drawn or played. Look in this order:
   - Design docs (`DESIGN.md`, `README`, GDD) for planned content.
   - Registries and data folders: characters, enemies, items, upgrades, weapons, stages
     (e.g. Godot `.tres` folders, JSON/YAML tables, enums).
   - Art code: sprite tables, texture loads, `load("res://...png")`, procedural drawing
     (`draw_circle`, `draw_rect`, generated tiles). Code-drawn visuals count too: floors, walls,
     bullets, particles, UI bars and panels, cursors.
   - Audio code: sound effect names passed to a play function, music track tables.
   Count from the code, don't estimate; say which counts you inferred (e.g. code-drawn UI).
3. **Write one entry per asset**, grouped with YAML comments by category (heroes, enemies, props,
   icons, UI, sfx, music). For each:
   - `id`: reuse the game's own name for it; `replaces`: the old name when it differs.
   - `size`: the size the game uses today (measure text-row sprites by row length × row count).
   - `frames`: what exists today at minimum. If the user wants a fuller animation pass, suggest
     typical counts (idle 2-4, walk 4-6, attack 3-4, hurt 1, death 4-6) and say they're suggestions.
   - `source`: the user's plan if known; otherwise `claude` for pixel art, `sfxr` for retro sound
     effects, `library` for realistic sound effects, `synth` for music. Ask if unsure for a whole
     category rather than per asset.
   - `file`: `sprites/<id>.png`, `tilesets/<id>.png`, `icons/<id>.png`, `ui/<id>.png`,
     `sfx/<id>.wav`, `voice/<id>.wav`, `music/<id>.ogg`, `fonts/<id>.png` (or `.ttf` / `.otf`).
   - Variants that are only a recolor or tint in the game (e.g. "champion" enemies) are **not**
     separate assets; note them on the base asset.
4. **Validate** with `validate --no-files` until it reports no problems.
5. **Report** with `status`, then give the user: total assets, total images (frames), the
   breakdown table, anything you inferred rather than counted, and a suggested first batch
   (the few assets that change the look the most, usually the player characters, common enemies
   and the floor).
