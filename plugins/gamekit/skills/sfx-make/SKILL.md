---
name: sfx-make
description: Make a game's sound effects: generate retro sounds with sfxr presets and tweak their parameters, write variants for the user to audition, or clean up downloaded sound files (trim, mono, normalize to 16-bit WAV), then check them. Use when the user wants sound effects created, replaced, tweaked ("deeper", "shorter", "less harsh") or imported from a sound library.
---

# Make sound effects

CLI (run from the game's root, the folder with `assets.yaml`; `python3` if `python` isn't found;
needs PyYAML and Pillow from `${CLAUDE_PLUGIN_ROOT}/requirements.txt`, ask before installing):

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" sfx new <id> --preset <name> [--seed N]
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" sfx make [ids]
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" sfx variants <id> [--count 5] [--preset <name>] [--amount 0.05]
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" sfx new <id> --from sounds/variants/<id>_<n>.yaml --force
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" sfx clean <file> <id> [--no-trim] [--peak -1] [--match <old.wav>] [--max-seconds S] [--force]
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" sfx info <id-or-file>...
python "${CLAUDE_PLUGIN_ROOT}/scripts/gamekit.py" check [ids]
```

Every sound comes out as game-ready WAV: mono, 16-bit, 44100 Hz, silence trimmed, peak at
-1 dBFS, a short fade-out. Downloaded mp3 / ogg / flac files need ffmpeg (the CLI says how to
install it if it's missing). For sounds from an imported pack, use `pack use` instead of
`sfx clean`: it cleans the same way and keeps the pack's license.

Peak level comes from `audio.sfx_peak_db` in `assets.yaml` (default -1 dBFS) unless `--peak` is given.

## You can't hear: use the numbers, and let the user listen

`sfx info` (also printed after `new`) describes a sound:

| Number | Meaning |
|---|---|
| seconds | Length. UI blips 0.05-0.2 s, hits 0.1-0.3 s, explosions 0.4-1 s |
| loudness (RMS) | How loud it feels. Keep sounds of the same family within a few dB; long noisy sounds feel louder than their peak suggests |
| attack | Time to full volume. 0-10 ms = snappy; slow attacks feel soft |
| brightness | Zero crossings per second: higher = higher-pitched or hissier |
| shape | Loudness over time, left to right (`@` loud, `.` quiet) |

Always tell the user which files to listen to (`assets/...wav`) and ask how they sound;
their ears decide, not the numbers.

## sfxr sounds (`source: sfxr`)

Parameters live in `sounds/<id>.yaml` (or the asset's `src`). Presets: `pickup` (coins, gems),
`laser` (shots), `explosion`, `powerup` (level up, buffs), `hit` (damage), `jump`, `blip` (UI),
`random`. Each `--seed` is a different random take on the preset.

How to change the sound by editing the YAML (then `sfx make <id>`):

| User says | Change |
|---|---|
| higher / lower | `base_freq` up / down (0.1 steps are big) |
| shorter / longer | `env_sustain` and `env_decay` down / up |
| punchier | `env_punch` up (0.3-0.6), `env_attack` 0 |
| softer, less harsh | `lpf_freq` down (0.5-0.8), `wave: sine` or `square` instead of `saw` |
| thinner / less boomy | `hpf_freq` up (0.1-0.3) |
| falling / rising pitch | `freq_ramp` negative / positive |
| wobble | `vib_strength` and `vib_speed` up |
| crunchy, retro rumble | `wave: noise` with a low `base_freq` (explosions, hits) |
| two-tone coin "ding" | `arp_speed` 0.5-0.7 and `arp_mod` 0.2-0.6 |
| quieter in the mix | leave the file at -1 dB peak; quieter is the game's job (its volume per sound) |

When the user can't describe what they want, run `sfx variants <id>` (small changes to the
current sound) or `sfx variants <id> --preset <name>` (fresh takes), ask them to listen to
`sounds/variants/<id>_*.wav`, then keep their pick with `sfx new <id> --from ... --force`.
Delete `sounds/variants/` once they've chosen.

## Downloaded sounds (`source: library`)

1. Only use sounds whose license the user has checked (Freesound: filter by CC0; Kenney, Sonniss
   GDC bundles: royalty-free). Never guess a license; record it on the asset
   (`license: {name, author, url}`) or import the download as a pack.
2. `sfx clean <file> <id>`. Use `--no-trim` for sounds with a deliberate quiet start, `--max-seconds` to cut a
   long sample (it fades out). **Replacing a sound a game already has?** Export the old one to WAV and pass
   `--match old.wav`: the new file gets the same loudness, so the game's mix doesn't change (the peak level
   is then only a ceiling). Very spiky sounds may stop at the ceiling, quieter than the old one; compress them
   first (ffmpeg `acompressor`) and clean again.
3. `check`, then tell the user to listen.

## Let the user choose by ear

Replacing many sounds at once? Don't install them and ask "how do they sound?". Build a listening
set instead and let the user pick:

1. For each sound, make 2-3 candidates (different files or layers) into a scratch folder, each
   loudness-matched to the current sound (`--match`), so the user compares character, not volume.
2. Copy the game's current sound next to them as `_old` (export the synth version if the game makes
   it in code). Name files `NN_<id>_old.wav`, `NN_<id>_A.wav`, `NN_<id>_B.wav`... so the user can
   answer by number and letter ("3 old, 4 B, 7 neither").
3. Zip the folder and send it to the user (it's a scratch file, not part of the game).
4. Apply the answers: install only the picks; for "old" set the asset back to its code source
   with `status: todo` and a note that the owner keeps it (so later sessions don't retry it); for
   "neither", make a new round from different sources. Expect the old sound to win often: it was
   tuned to the game.

Don't reuse a rejected file in the next round unless the mix is clearly different, and say so.

## Finish

Set the asset's `status: draft` in `assets.yaml` (keep the file's comments and layout); `done`
once the user is happy with it in the game. Run `validate` and, for downloaded sounds, `credits`.
