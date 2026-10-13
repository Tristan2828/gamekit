---
name: picture-make
description: Make pictures from a description on the user's own PC with the local picture engine (FLUX.2 klein), for concept art, references for pixel sprites, icons, seamless textures and character turnarounds, cut a subject out of its background (BiRefNet), and turn a picture into an image asset (shrunk to size, palette-snapped). Use when the user wants an AI picture, a texture, concept art, a reference to draw from, a transparent background, or asks to set up the picture or cut-out engine.
---

# Make pictures with the local picture engine

CLI (run from the game's root, the folder with `assets.yaml`; `python3` if `python` isn't found):

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" engines list
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" engines setup picture      # once per PC; ask first (several GB)
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" picture "<description>" [--takes 2] [--size 1024x1024] [--tile] [--seed N] [--from <picture.png>] [--for <asset-id>]
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" engines setup cutout       # small (~300 MB, no PyTorch); fine to run
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" picture-cutout <picture.png> [more.png...]
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" picture-use <picture.png> <asset-id> [--frame <name>_walk_1] [--keep-background] [--no-palette] [--no-outline] [--force]
```

The user can do all of this on the Pictures tab of the asset page (`gamekit ui`), which is easier for them:
pictures appear as they're made, with Keep / Another take / Work from this / Cut out / Use as asset buttons.

## How it runs

- The engine is a separate Python with PyTorch for the PC's graphics card (AMD on Windows: ROCm; NVIDIA:
  CUDA), under `%LOCALAPPDATA%\gamekit\engines`. The model (FLUX.2 klein 4B, Apache 2.0, about 16 GB)
  downloads on first use into `engines\models`. Nothing goes into the game or the plugin.
- Pictures go to the game's `pictures/` folder, each with a `.json` of what made it (description, seed, size).
  Removed ones move to `pictures/_removed/`. Suggest git-ignoring `pictures/` unless the user wants them kept.
- Timing on a 16 GB card: loading ~30 s; a new description ~30 s; more takes of the same description ~8 s.
  The model runs one picture at a time and the CLI loads it per command, so prefer `--takes N` over
  several commands.
- Cut-outs: a second engine, `cutout` (BiRefNet lite as ONNX, MIT, ~210 MB), on the processor (~8 s a picture),
  so it runs beside the picture model. `picture-cutout` writes `<name>-cutout.png` with a transparent background
  and a `.json` with `cutout_of`.
- Logs: `%LOCALAPPDATA%\gamekit\engines\logs\picture.log`. Out-of-memory or very slow pictures on a smaller
  card: `GAMEKIT_PICTURE_MODE=offload`.

## Writing descriptions

- Say the style first, then the subject, then the setting: "pixel art sprite of a hooded cultist holding a
  candle, dark fantasy, full body, plain white background". FLUX.2 klein draws clean pixel-art sprites from
  "pixel art sprite, ..., clean dark outline, limited color palette, plain white background, game asset" without
  any add-on (a pixel-art LoRA was tried and was slower and worse).
- For anything that becomes a sprite or icon: **plain white background**, whole subject in view, centered.
- Textures: "seamless ... texture, top down, even lighting" plus `--tile`.
- Turnarounds (and later 3D models): "character design, A-pose, front view, plain white background", then
  `--from` that picture with "the same character from behind" for the back.
- Look at every result (Read the PNG) before showing or using it, and say honestly what's off.

## Pictures and pixel art sprites

`picture-use` removes a plain background (a flood fill from the corners; a picture that is already transparent,
such as a cut-out, keeps its own), crops to the subject, shrinks it to the asset's size (bottom-centered), and
snaps to the palette by hue: each sprite pixel takes its patch's most common palette color, so eyes and accents
survive. It sets the asset's `source: ai` (and `todo` -> `draft`).

- The manifest's `sprites:` block holds the game's rules: `prompt` (words that start descriptions made for a
  sprite), `outline` (1 px outline color drawn inside the size; `--no-outline` skips it) and `reserved_colors`
  (never snapped to, e.g. player colors). Read it before writing a description or using a picture.
- Descriptions for a sprite: start with its grid, "a 12x12 pixel art sprite, each pixel a clean square block",
  then the `sprites.prompt` words, "plain white background, whole body in view" and the look (the asset's
  `notes`). Chunky, chibi proportions with big eyes survive shrinking far better than realistic ones. Pass
  `--for <asset-id>` so the files are named after the asset.
- Animated sprites (manifest `frame_files: true`): one picture per frame. Make the base pose, then
  `--from <base.png>` with only the pose ("the same creature, same colors and style, walking, left foot
  forward"), and `picture-use ... --frame shambler_walk_1`. Sheets (no frame_files): draw with `art-draw`.
- Run `picture-cutout` before using a picture as a sprite.
- Expect: 18 px and up usable drafts; 10 to 14 px readable blobs; smaller or very wide (14x8) loses the face.
  For those, **redraw instead**: look at the picture (Read the PNG) and draw the sprite with the `art-draw`
  skill (silhouette, outline, a few palette colors), then say it was drawn from the picture.
- Look at the result (Read the asset PNG, zoomed) before calling it done, and say honestly what's off.
- Shrinking works well for textures (`tileset` assets fill the whole tile, no outline) and larger art.

AI pictures are the game's own (`source: ai` credits them as "made with a local AI model"); no license entry is
needed. Never pass off a picture made to imitate a named living artist's style.
