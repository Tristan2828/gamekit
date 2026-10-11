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

Needs Python 3.10+ with PyYAML (`python -m pip install -r plugins/gamekit/requirements.txt`).
Later steps also use Aseprite, ffmpeg and Godot (see the roadmap).

## Skills

| Skill | Use it to |
|---|---|
| `/gamekit:assets-plan` | Survey a game's code and docs and list every asset it needs in `assets.yaml` |
| `/gamekit:assets-status` | See what's left, mark assets done, record licenses, regenerate `CREDITS.md` |

The same tools work without Claude, from the game's folder:

```
python <gamekit>/plugins/gamekit/scripts/gamekit.py init --game "My Game"
python <gamekit>/plugins/gamekit/scripts/gamekit.py validate
python <gamekit>/plugins/gamekit/scripts/gamekit.py status --todo
python <gamekit>/plugins/gamekit/scripts/gamekit.py credits
```

## Roadmap

| Step | What | Status |
|---|---|---|
| 1 | Plugin skeleton, `assets.yaml` manifest, palette files (.hex / .gpl), `CREDITS.md`, plan + status skills | ✅ done |
| 2 | Art: Claude's text-row sprites → PNG on the palette, palette check, preview sheet, Aseprite CLI export | next |
| 3 | Pack import: unzip, rename, record license, optional recolor to the palette | |
| 4 | Sound effects: ffmpeg clean-up (trim, mono, loudness, WAV), then an sfxr-style generator with presets | |
| 5 | Music: render text scores with Godot headless, export looping OGG | |
| 6 | First real use: GameTest's first batch (heroes, enemies, floors) | |

## Develop

```
python -m unittest discover -s tests
claude plugin validate .
```
