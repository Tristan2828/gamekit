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
| `/gamekit:picture-make` | Make pictures from a description on your own PC (concept art, references, icons, seamless textures) and turn one into an asset |
| `/gamekit:voice-make` | Voice-overs read in a voice you describe, on your own PC |
| `/gamekit:music-make` | Render the game's own music through Godot, or convert downloaded / AI music, into looping OGGs with checked loop points |

## The asset page

A Hearthtone-style page in your browser for the same tools: progress and every asset with its
preview or player, sound takes to audition and tweak ("higher", "punchier"...), music players with
loudness and loop numbers, render and import buttons, and a pixel art gallery. It reads and edits
the game's `assets.yaml`, so Claude and the page always agree.

```
python <gamekit>/plugins/gamekit/scripts/gamekit.py ui            # opens the page (http://127.0.0.1:7862)
python <gamekit>/plugins/gamekit/scripts/gamekit.py ui --launcher # writes 'Start Gamekit.bat': double-click it next time
```

It opens as its own window in Brave, Chrome or Edge (the first one found; set `GAMEKIT_BROWSER` to a
browser's .exe to choose), or as a tab in your default browser.
It only answers this PC, and needs nothing beyond PyYAML and Pillow. Leave its window open while you
use the page; close it to quit.

**How to use it, tab by tab: [docs/asset-page.md](docs/asset-page.md).**

### Local AI engines

The Pictures tab runs an AI model on your own graphics card: no account, no limits. Each engine is its own
Python with PyTorch for your card (AMD on Windows via ROCm 7.2.1, NVIDIA via CUDA), kept in
`%LOCALAPPDATA%\gamekit\engines`; models download on first use (pictures: FLUX.2 klein 4B, Apache 2.0, ~16 GB).
Set one up from the page or with `gamekit.py engines setup picture` (needs [uv](https://docs.astral.sh/uv/):
`winget install astral-sh.uv`). Music: ACE-Step 1.5 (MIT, ~10 GB; its code is fetched with git at a pinned
commit). Voices: Qwen3-TTS VoiceDesign (Apache 2.0, ~4 GB). Sounds: Stable Audio 3 Small SFX (Stability AI
Community License, gated: accept it once on Hugging Face). The workers are adapted from Hearthtone's, with thanks.

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
python <gamekit>/plugins/gamekit/scripts/gamekit.py sfx clean <file> <asset> [--match old.wav]    # any sound -> clean WAV
python <gamekit>/plugins/gamekit/scripts/gamekit.py sfx info <asset-or-file>
python <gamekit>/plugins/gamekit/scripts/gamekit.py music render [assets]                       # game's Godot script -> OGG
python <gamekit>/plugins/gamekit/scripts/gamekit.py music clean <file> <asset> --end 64.0        # any music -> OGG, -16 LUFS
python <gamekit>/plugins/gamekit/scripts/gamekit.py music info <asset-or-file>
```

Sound effects come out as mono 16-bit 44100 Hz WAV, trimmed and normalized to -1 dBFS.
Reading mp3 / ogg / flac and making music needs [ffmpeg](https://ffmpeg.org) (Windows: `winget install ffmpeg`).
Music comes out as looping Ogg Vorbis; `check` reports clicks and gaps at the loop point.
`music render` runs the game's own Godot script (template: `plugins/gamekit/templates/godot/render_music.gd`);
Godot is found via `GAMEKIT_GODOT`, PATH or common install folders.

Animated sprites become a sheet (one row per animation, frames left to right) with a JSON
sidecar next to the PNG listing each frame's position, or, with `frame_files: true` in
`assets.yaml`, one PNG per frame (`hero.png`, `hero_1.png`, `hero_walk_1.png`, `hero_attack.png`). A sheet's sidecar:

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
| 5 | Music: render the game's scores with Godot headless or convert music files, looping OGG, loudness, loop checks | ✅ done |
| 6 | First real use in GameTest: game loads files; heroes, card icons, 9 music tracks, 7 sound effects (picked by ear from 2 rounds of candidates) | ✅ done |
| 7 | Asset page (`gamekit ui`): assets, sounds, music and art tabs in the browser | ✅ done |
| 8 | Local AI engines: tested on an AMD RX 7800 XT (ROCm on Windows); **Pictures** tab with FLUX.2 klein (~8 s a take) | ✅ done |
| 9 | **Music** engine: ACE-Step 1.5 on AMD (~1.5 s per second of music), AI takes on the Music tab, "use for a track" with loop cut | ✅ done |
| 10 | **Voices** tab (Qwen3-TTS, ~2x real time) and AI **sound effects** (Stable Audio 3, ~0.3 s a sound; gated license, accepted once per person) | ✅ done |
| 11 | 3D models (Hunyuan3D 2), texturing, rigging via Blender | planned |

## Develop

```
python -m unittest discover -s tests
claude plugin validate .
```
