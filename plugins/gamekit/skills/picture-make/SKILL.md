---
name: picture-make
description: Make pictures from a description on the user's own PC with the local picture engine (FLUX.2 klein), for concept art, references for pixel sprites, icons, seamless textures and character turnarounds, and turn a picture into an image asset (shrunk to size, palette-snapped). Use when the user wants an AI picture, a texture, concept art, a reference to draw from, or asks to set up the picture engine.
---

# Make pictures with the local picture engine

CLI (run from the game's root, the folder with `assets.yaml`; `python3` if `python` isn't found):

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" engines list
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" engines setup picture      # once per PC; ask first (several GB)
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" picture "<description>" [--takes 2] [--size 1024x1024] [--tile] [--seed N] [--from <picture.png>]
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" picture-use <picture.png> <asset-id> [--keep-background] [--no-palette] [--force]
```

The user can do all of this on the Pictures tab of the asset page (`gamekit ui`), which is easier for them:
pictures appear as they're made, with Keep / Another take / Work from this / Use as asset buttons.

## How it runs

- The engine is a separate Python with PyTorch for the PC's graphics card (AMD on Windows: ROCm; NVIDIA:
  CUDA), under `%LOCALAPPDATA%\gamekit\engines`. The model (FLUX.2 klein 4B, Apache 2.0, about 16 GB)
  downloads on first use into `engines\models`. Nothing goes into the game or the plugin.
- Pictures go to the game's `pictures/` folder, each with a `.json` of what made it (description, seed, size).
  Removed ones move to `pictures/_removed/`. Suggest git-ignoring `pictures/` unless the user wants them kept.
- Timing on a 16 GB card: loading ~30 s; a new description ~30 s; more takes of the same description ~8 s.
  The model runs one picture at a time and the CLI loads it per command, so prefer `--takes N` over
  several commands.
- Logs: `%LOCALAPPDATA%\gamekit\engines\logs\picture.log`. Out-of-memory or very slow pictures on a smaller
  card: `GAMEKIT_PICTURE_MODE=offload`.

## Writing descriptions

- Say the style first, then the subject, then the setting: "pixel art sprite of a hooded cultist holding a
  candle, dark fantasy, full body, plain white background".
- For anything that becomes a sprite or icon: **plain white background**, whole subject in view, centered.
- Textures: "seamless ... texture, top down, even lighting" plus `--tile`.
- Turnarounds (and later 3D models): "character design, A-pose, front view, plain white background", then
  `--from` that picture with "the same character from behind" for the back.
- Look at every result (Read the PNG) before showing or using it, and say honestly what's off.

## Pictures and pixel art sprites

`picture-use` removes a plain background, crops to the subject, shrinks it to the asset's size (bottom-centered),
makes edges hard and snaps colors to the palette; it sets the asset's `source: ai` (and `todo` -> `draft`).

- **Small sprites (under ~24 px): don't shrink pictures; redraw them.** Shrinking a painting to 16x16 gives
  speckled, outline-less pixels. Use the picture as a reference and draw the sprite yourself with the
  `art-draw` skill (silhouette, outline, a few palette colors), then say it was drawn from the picture.
- Shrinking works for textures (`tileset` assets fill the whole tile), backgrounds and larger art.
- Check for palette colors with a special meaning in the game (e.g. GameTest's magenta = player color) after
  snapping; `--no-palette` keeps the picture's own colors.
- Animated sprites: a picture makes one frame; draw the animation with `art-draw`.

AI pictures are the game's own (`source: ai` credits them as "made with a local AI model"); no license entry is
needed. Never pass off a picture made to imitate a named living artist's style.
