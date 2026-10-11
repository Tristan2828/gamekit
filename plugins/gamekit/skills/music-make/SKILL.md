---
name: music-make
description: Turn a game's music into looping Ogg Vorbis files - render the game's own code-made music (text scores, synths) through Godot headless, or convert downloaded, commissioned or AI-generated music files - with even loudness and a check that each track loops without a click or gap. Use when the user wants music files for the game, a new or replaced track, louder/quieter music, or a loop fixed.
---

# Make music files

CLI (run from the game's root, the folder with `assets.yaml`; `python3` if `python` isn't found;
needs PyYAML and Pillow from `${CLAUDE_PLUGIN_ROOT}/requirements.txt`, ask before installing;
**needs ffmpeg**):

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" music render [ids] [--loudness -16] [--keep-wav <folder>]
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" music clean <file> <id> [--loudness -16 | --keep-level] [--start s] [--end s] [--force]
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" music info <id-or-file>...
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" check [ids]
```

Music comes out as Ogg Vorbis, 44100 Hz (stereo kept), quality 5. It is never trimmed or faded
(that would break the loop). Loudness is changed with one fixed gain for the whole track, so the
loop stays seamless; -16 LUFS is a common level for game music. Music loops unless the asset
says `loop: false`.

## The game's own music (`source: synth`)

`music render` runs the game's Godot render script, which must write `<out>/<track>.wav` for every
`--track=<name>` (the track name is the asset's `replaces`, else its id). Set it up once:

1. Copy `${CLAUDE_PLUGIN_ROOT}/templates/godot/render_music.gd` to the game's `tools/` and fill in
   `render()` with the game's own music code. Scripts run with `-s` get no autoloads: call the
   plain classes (`class_name`) that build the music. Statically type it if the project requires it.
2. In `assets.yaml`:
   ```yaml
   music:
     godot_project: .
     render_script: tools/render_music.gd
   ```
3. Godot is found via `$GAMEKIT_GODOT`, PATH, or common install folders. If the game's CLAUDE.md
   names the Godot executable, set `GAMEKIT_GODOT` to it (on Windows use the `*_console.exe`).
   The project must have been imported once (`Godot --headless --path . --import`) so class
   names resolve.

Rendering keeps the game's own mix level; add `--loudness` only to match other music.

## Downloaded, commissioned or AI music (`source: library` / `commission`)

1. Check the license first and record it on the asset (`license: {name, author, url}`) or import
   the download as a pack (`pack use` makes OGGs at -16 LUFS). AI music services differ: some
   free tiers forbid commercial use. Never guess a license.
2. `music clean <file> <id>`. To make a song loop, cut it at musical points with `--start` /
   `--end` (seconds, ideally on a bar line: bar length = 4 x 60 / BPM for 4/4). Songs with a
   fade-out or intro need cutting, or `loop: false`.

## Checking loops (you can't listen; the user can)

`music info` and `check` report, per track:

| Number | Meaning |
|---|---|
| LUFS | Loudness. Keep the game's tracks within ~2 LU of each other |
| true peak | Above 0 dBTP clips; re-encode with `--loudness` |
| loop point jump | How far the waveform jumps from the last sample to the first, next to its normal movement. A much bigger jump clicks on every loop |
| silence at end + start | A pause each time the track loops. Over 1 s is reported; shorter can be a deliberate rest |

"Can't be measured exactly" means ffmpeg decoded the file a few samples long or short (common
for short Ogg files); the file itself is fine, and `render` checks the WAV instead.

Tell the user which files to listen to, ideally looping (any player with repeat on), and ask.

## Using the files in Godot

Godot plays an imported `.ogg` once unless looping is on: either tick **Loop** in the file's
Import dock, or set it in code when loading (`stream.loop = true` on the `AudioStreamOggVorbis`).

## Finish

Set each asset's `status: draft` in `assets.yaml` (keep its comments and layout), `done` once the
user approves it in the game. Run `validate`, and `credits` for licensed music.
