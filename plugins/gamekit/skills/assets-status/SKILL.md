---
name: assets-status
description: Report progress on a game's assets from its assets.yaml manifest, check the manifest for mistakes, mark assets as draft or done, record licenses for downloaded assets, and regenerate CREDITS.md. Use when the user asks what's left to make, how far the art or audio is, whether credits are complete, or after adding finished asset files.
---

# Asset status, licenses and credits

Run the CLI from the game's root folder (the one with `assets.yaml`):

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" <command>
```

Use `python3` if `python` isn't found. If PyYAML is missing, run
`python -m pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"` (ask the user first).
If there's no `assets.yaml`, use the `assets-plan` skill first.

| Command | Does |
|---|---|
| `status` | Counts per kind: todo / draft / done / keep, total assets and images |
| `status --todo` | Also lists every unfinished asset with size, frames, source and file |
| `validate` | Checks the manifest, the palette file, and that every `done` asset's file exists |
| `credits` | Writes `CREDITS.md` from the license info (third-party authors + what was made in-house) |

The user can also see all this in a browser: `gamekit ui` opens the asset page (progress, previews,
players, status buttons); `gamekit ui --launcher` writes a `Start Gamekit.bat` to double-click.
It edits `assets.yaml` too, so read the file again before changing it if the page may be open.

## Updating the manifest

Edit `assets.yaml` directly, then run `validate`.

- **A file arrived** (exported, downloaded, generated): set `status: draft` while it still needs
  cleanup or review in-game, `done` when the user is happy with it. `validate` fails if a `done`
  asset's file is missing from the output folder.
- **The game keeps its own version** (the owner chose its code-drawn sprite or synth sound over a
  new file): `status: keep`, with a note saying so. It counts as finished and needs no file or license.
- **Downloaded or commissioned asset** (`source: pack`, `library`, `commission`): for an imported
  pack use `license: {pack: <name>}` (see the `pack-import` skill); otherwise fill
  `license: {name, author, url}` from the pack's license file or download page. Never guess a
  license. If it's unclear, leave the asset at `todo`/`draft`, and tell the user what to check.
  CC-BY and similar licenses require the credit to ship with the game.
- **Credits**: run `credits` after any license change and remind the user to ship `CREDITS.md`
  (or show it in-game).

## Reporting

Lead with the percentage done (done + keep) and the counts table. Then list what blocks a release: assets still
`todo`, `draft` assets, and any licensed asset missing license info.
