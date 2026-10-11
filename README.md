# Gamekit

A Claude Code plugin for making a game's art and audio: plan every asset in one manifest, then make
or find each one (Claude-drawn pixel art, your own Aseprite files, ready-made packs, procedural
sound effects, rendered music), with licenses and credits tracked along the way.

```
                 assets.yaml  (one entry per asset: size, frames, source, license, status)
                      │
   ┌──────────────────┼───────────────────────────────┐
   ▼                  ▼                               ▼
 art                 sfx                            music
 claude / self / pack   sfxr / library                synth (text scores)
   │                  │                               │
   └──────► assets/sprites  assets/sfx/*.wav  assets/music/*.ogg ──► CREDITS.md
```

## Install

In Claude Code:

```
/plugin marketplace add Tristan2828/gamekit
/plugin install gamekit@gamekit
```

Needs Python 3.10+ with PyYAML and Pillow (`python -m pip install -r plugins/gamekit/requirements.txt`).
Optional programs: Aseprite (exporting your own art), ffmpeg (mp3 / ogg / flac sounds, music), Godot (music rendering).

## Skills

| Skill | Use it to |
|---|---|
| `/gamekit:assets-plan` | Survey a game's code and docs and list every asset it needs in `assets.yaml` |
| `/gamekit:assets-status` | See what's left, mark assets done, record licenses, regenerate `CREDITS.md` |
| `/gamekit:art-draw` | Have Claude draw a sprite as text rows, render it to PNG and review it |
| `/gamekit:art-export` | Export your `.aseprite` files with the Aseprite CLI; check any image's size, frames and palette |
| `/gamekit:pack-import` | Import a downloaded pack, record its license, and cut sprites, frames or sounds out of it |
| `/gamekit:sfx-make` | Generate retro sound effects (sfxr presets), tweak and audition variants, or clean up downloaded sounds |

The same tools work without Claude, from the game's folder:

```
python <gamekit>/plugins/gamekit/scripts/gamekit.py init --game "My Game"
python <gamekit>/plugins/gamekit/scripts/gamekit.py validate
python <gamekit>/plugins/gamekit/scripts/gamekit.py status --todo
python <gamekit>/plugins/gamekit/scripts/gamekit.py credits
python <gamekit>/plugins/gamekit/scripts/gamekit.py draw [ids]       # art/<id>.yaml -> PNG
python <gamekit>/plugins/gamekit/scripts/gamekit.py export [ids]     # art/<id>.aseprite -> PNG
python <gamekit>/plugins/gamekit/scripts/gamekit.py check [ids]
python <gamekit>/plugins/gamekit/scripts/gamekit.py preview [ids] --scale 8
python <gamekit>/plugins/gamekit/scripts/gamekit.py pack add <zip> <name>     # then: pack info / pack license
python <gamekit>/plugins/gamekit/scripts/gamekit.py pack use <name> <file> <asset> [--crop x,y,w,h] [--anim walk=0,16,4] [--resize 16x16] [--recolor]
python <gamekit>/plugins/gamekit/scripts/gamekit.py sfx new <asset> --preset explosion --seed 2   # sounds/<id>.yaml -> WAV
python <gamekit>/plugins/gamekit/scripts/gamekit.py sfx variants <asset> --count 5               # versions to listen to
python <gamekit>/plugins/gamekit/scripts/gamekit.py sfx clean <file> <asset>                     # any sound -> clean WAV
python <gamekit>/plugins/gamekit/scripts/gamekit.py sfx info <asset-or-file>
```

Sound effects come out as mono 16-bit 44100 Hz WAV, trimmed and normalized to -1 dBFS.
Reading mp3 / ogg / flac needs [ffmpeg](https://ffmpeg.org) (Windows: `winget install ffmpeg`).

Animated sprites become a sheet (one row per animation, frames left to right) with a JSON
sidecar next to the PNG listing each frame's position:

```json
{"image": "hero.png", "frame_size": [16, 16], "animations": {"idle": [[0, 0], [16, 0]], "walk": [[0, 16], ...]}}
```

## Roadmap

| Step | What | Status |
|---|---|---|
| 1 | Plugin skeleton, `assets.yaml` manifest, palette files (.hex / .gpl), `CREDITS.md`, plan + status skills | ✅ done |
| 2 | Art: Claude's text-row sprites → PNG on the palette, palette check, preview sheet, Aseprite CLI export | ✅ done |
| 3 | Pack import: unzip, record license, crop / slice / resize / recolor into assets | ✅ done |
| 4 | Sound effects: sfxr generator with presets and variants, clean-up of any sound file to WAV, sound checks | ✅ done |
| 5 | Music: render text scores with Godot headless, export looping OGG | next |
| 6 | First real use: GameTest's first batch (heroes, enemies, floors) | |

## Develop

```
python -m unittest discover -s tests
claude plugin validate .
```
