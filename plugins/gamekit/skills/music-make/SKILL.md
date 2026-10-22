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
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" music make "<description>" [--seconds 60] [--takes 2] [--bpm 70] [--key "D minor"] [--lyrics "..."] [--planner]
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" music use <take.wav> <id> [--start s] [--end s] [--force]
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" check [ids]
```

Music comes out as Ogg Vorbis, 44100 Hz (stereo kept), quality 5. It is never trimmed or faded
(that would break the loop). Loudness is changed with one fixed gain for the whole track, plus a
gentle peak limiter when the loudest hits would otherwise clip (the output says by how much), so the
loop stays seamless; -16 LUFS is a common level for game music. Music loops unless the asset
says `loop: false`.

## AI music on the user's PC (`music make`)

The music engine runs ACE-Step 1.5 (MIT) on the PC's graphics card; set it up once with
`gamekit.py engines setup music` (ask first: several GB) or the Music tab's **Set up** button.
Takes go to the game's `music-takes/` folder (a `.json` beside each holds the settings); suggest git-ignoring it.

- Describe instruments, mood and place: "Instrumental music for a flooded abbey: slow monastic choir humming,
  a deep tolling bell, low strings; mournful, misty". Add "steady, loopable, no intro, no ending" for loops.
- On an RX 7800 XT: loading ~40 s, then ~1.5 s per second of music. `--planner` (better structure) takes
  ~7 minutes a take on AMD and once failed with an OverflowError there: only when the user asks.
- You can't listen: read `music info` and the shape, then **ask the user to listen** (the Music tab plays every
  take). They pick; then `music use <take> <id> --end <s>` makes the looping OGG and sets `source: ai`.
- AI tracks rarely loop by themselves and often fade out: check `music info`'s loop numbers after `use`, and
  cut with `--start`/`--end` (re-run with `--force`) at a point the user confirms by ear.

Loudness comes from `audio.music_lufs` in `assets.yaml` unless `--loudness` is given (`music clean` falls back to -16 LUFS; `music render` to the game's own mix).

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

### Making a short code-made loop longer

A 10-30 s loop gets tiring fast; game music briefs usually ask for 60-120 s with an A and a B section.
`music info <id>` shows the length. To lengthen one, edit the game's text score (not the OGG):

1. Read the track's score and the brief. Keep its key, tempo, instruments and mood.
2. Keep the existing phrase as section A. Write a B section that answers it: the same chords in another
   order or a step up, a melody variation, or a breakdown (drums and bass only), 8-16 bars.
3. Arrange A A B A (or A B A C) so the total lands in 60-120 s, and make the last bar lead back into
   the first so the loop seam stays smooth.
4. Run the game's own tests if it has any, then `music render <id>` (needs Godot on the user's PC) and
   check the numbers: same loudness as the other tracks, no silence at the start or end, no loop jump.
   Ask the user to listen in game before marking it done.

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
