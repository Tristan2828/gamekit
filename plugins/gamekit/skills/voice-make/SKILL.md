---
name: voice-make
description: Make voice-overs on the user's own PC with the local voice engine (Qwen3-TTS VoiceDesign): spoken lines read in a voice described in plain words (narrator, villain, shopkeeper, creature...), and turn a reading into a game asset. Use when the user wants voice lines, dialogue audio, narration, barks or announcer lines.
---

# Make voice-overs with the local voice engine

CLI (run from the game's root, the folder with `assets.yaml`; `python3` if `python` isn't found):

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" engines setup voice        # once per PC; ask first (a few GB)
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" voice "<words>" --who "<the voice>" --tone "<how it's said>" [--takes 2] [--seed N] [--language English]
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" take-use voice <take.wav> <asset-id> [--force]
```

The user can do the same on the **Voices** tab of the asset page (`gamekit ui`), with ready-made voices
(narrator, innkeeper, villain, hero, creature, child) and a player for every reading. Prefer that for choosing.

- Model: Qwen3-TTS 1.7B VoiceDesign (Apache 2.0), about 4 GB, on the graphics card. On an RX 7800 XT:
  loading ~35 s, a 7-second line ~19 s, short lines a few seconds.
- Readings go to the game's `voice-takes/` folder with a `.json` of the words, voice, tone and seed.
- Three separate fields: **words** (only what's said, up to 1,500 characters a reading), **who** (age, man or
  woman, the sound of the voice, accent, pace) and **tone** (whispering, shouting across a field, weary...).
- The same `--who` text gives a similar voice, not an identical one. For a character with many lines, find a take
  the user likes, then reuse its seed and keep `--who` exactly the same.
- You can't listen: ask the user to listen and pick. Then `take-use voice` makes the asset's WAV (mono, 16-bit,
  44100 Hz, trimmed, the game's peak level) and sets `source: ai` (`todo` -> `draft`).
- Voice assets use `kind: voice` (`.wav`, no 5-second limit like `sfx`). Add entries for lines the game needs;
  `notes` can hold the words.
- Never imitate a real, named person's voice.
