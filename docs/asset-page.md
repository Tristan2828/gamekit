# Using the asset page

The asset page is gamekit in your browser. It shows every asset your game needs (from `assets.yaml`),
lets you listen to and pick sounds, play your music, look at your sprites, and mark things done.
It changes the same `assets.yaml` file Claude uses, so you and Claude always see the same list.

## Open it

In PowerShell, from your game's folder (the one with `assets.yaml`):

```
python C:\Repos\gamekit\plugins\gamekit\scripts\gamekit.py ui
```

A window opens (Brave, Chrome or Edge). **Leave the PowerShell window open** while you use the page;
press Ctrl+C there (or close it) to quit.

Easier next time: run this once and a `Start Gamekit.bat` appears in the game folder. Double-click it.

```
python C:\Repos\gamekit\plugins\gamekit\scripts\gamekit.py ui --launcher
```

If Claude or you edit `assets.yaml` while the page is open, press **Refresh** (top right).
**Folder** opens the game folder in File Explorer.

## Words you'll see

| Word | Meaning |
|---|---|
| **todo** | Not made yet (or the game still uses its old placeholder). |
| **draft** | A file exists but isn't final. Making a file on the page moves an asset to draft by itself. |
| **done** | You're happy with it in the game. Only you set this. |
| **source** | Where the asset comes from: `claude` (Claude draws it), `sfxr` (made by the sound generator), `synth` (your game's own music code), `pack` / `library` (downloaded), `self` (you make it in Aseprite). |
| **take** | One try at a sound. You make a few, listen, and keep the best. |

The **todo / draft / done** buttons under every asset change its status straight away.

## Assets tab: what's left

- **Progress** (left): how much is done, and a table per kind (sprites, icons, sounds, music...).
- **Show**: filter by kind or status, or search. "Not done" hides finished things: a handy to-do list.
- The list (right): every asset with a small preview or a player, its size and animation frames, and notes.
- **Checks**:
  - **Check the manifest**: finds mistakes in `assets.yaml` (typos, missing sizes, missing licenses).
  - **Check the files**: checks made files are the right size, use the palette's colors, and that sounds aren't silent or distorted.
  - **Write CREDITS.md**: lists who made the downloaded assets. Ship it with the game.

## Sounds tab: make and pick sound effects

1. **Pick a sound** at the top left (e.g. `sfx_shoot`). Its current sound, if any, plays below.
2. **Make takes**: pick a preset that's close to what you want (`hit`, `laser`, `explosion`,
   `pickup`, `jump`, `blip`, `powerup`, or `random`), set how many takes, and press **Make takes**.
3. **Listen** to the takes on the right. Each one shows its length, loudness and a little shape
   (tall at the start = punchy, long tail = rings out).
4. **Change one you almost like** with the buttons under it. Each makes a new take:

   | Button | Does |
   |---|---|
   | higher / lower | Pitch up or down |
   | shorter / longer | Length |
   | punchier | Hits harder at the start |
   | softer | Less harsh, duller |
   | thinner / fuller | Less or more bass |
   | falling / rising | Pitch slides down or up |
   | wobble / steady | Add or remove vibrato |

   **More like this** makes 3 small random variations of that take.
5. **Keep this one** makes that take the game's sound (it writes the WAV the game loads) and moves
   the asset to draft. Then play the game and judge it there.
6. **Clear takes** deletes the takes when you're done choosing (they're scratch files in `sounds/variants/`).

**Takes similar to the current sound** works once a sound has been kept: small changes to it.

### Using a downloaded sound instead

1. Drop the file (`.wav`, `.mp3`, `.ogg`, `.flac`) on **Or import a sound file**, or click it to choose.
2. Options: **Trim silence** (leave on unless the sound starts quietly on purpose), **Cut to at most**
   (shortens a long sound with a fade), and **Match the loudness of**: drop the sound it replaces there
   so the new one is just as loud.
3. Press **Import**. It becomes a clean game-ready WAV. If the asset already has a file, you're asked first.
4. Downloaded sounds need their license written down. Tell Claude where it came from; never guess a license.

## Music tab: play, render and import music

- **Every track** (right) has a player. Looping tracks loop.
- Pick a track at the top left to see its numbers:
  - **LUFS**: how loud it feels. Tracks should be about the same (your game uses -16).
  - **true peak**: should stay below 0, or it distorts.
  - **loop jump** and **silence across it**: whether the loop point clicks or pauses. A small jump
    (close to the "normal" number) and almost no silence means a clean loop.
- **Render this track / Render every synth track** runs your game's own music code through Godot
  and saves the OGG files the game plays. Takes a minute or more.
- **Import a music file**: drop a file, optionally set **Start** and **End** (in seconds) to pick the
  part that loops, and press **Import**. It's converted to OGG at the game's loudness.
  **Keep its own loudness** skips that. Needs ffmpeg (already installed on your PC).

## Art tab: look at your sprites

- A gallery of every image, enlarged with crisp pixels. Use **Zoom** to change the size.
- Empty dashed boxes are images not made yet; the box shows the size the game expects.
- Animated sprites show all their frames together.
- **Draw** (for `claude` assets): Claude writes each sprite as text in `art/<id>.yaml`. To get a new or
  changed sprite, ask Claude (e.g. "draw the bat"). If you edit the text file yourself, press
  **Draw** to turn it into the PNG.
- **Export** (for `self` assets): turns your Aseprite file into the PNG. Needs Aseprite.
- **Check** / **Check the images**: size and palette problems, listed at the top.

## A typical session

1. Open the page and go to **Assets**. Set Status to **Not done** to see what's left.
2. Sounds: **Sounds** tab, pick a sound, make takes, tweak, **Keep** the best.
3. Play the game. Happy with it? Mark the asset **done**.
4. Sprites: ask Claude to draw a batch, then look at them on the **Art** tab and mark the good ones done.
5. Before a release: **Check the manifest**, **Check the files**, and **Write CREDITS.md**.

## When something goes wrong

| Problem | Fix |
|---|---|
| `gamekit` is not recognized | Use the full command: `python C:\Repos\gamekit\plugins\gamekit\scripts\gamekit.py ui` |
| "not found. Run `gamekit init` first" | Run it from the game folder (the one with `assets.yaml`). |
| The window doesn't open | Open the address printed in PowerShell (`http://127.0.0.1:7862`) in any browser. |
| "no answer from gamekit" | The PowerShell window was closed. Start it again. |
| "still busy" | Another action (like rendering music) is running. Wait for it to finish. |
| Changes made by Claude don't show | Press **Refresh**. |
| A player shows the wrong length | The browser guesses until the track has loaded; press play. |
