# Using the asset page

The asset page is gamekit in your browser. It shows every asset your game needs (from `assets.yaml`), lets you
make and pick sounds, music, pictures and voice-overs, look at your sprites, and mark things done. It changes the
same `assets.yaml` file Claude uses, so you and Claude always see the same list.

| Tab | What it's for |
|---|---|
| **Assets** | What's left: progress, every asset with a preview or player, status buttons, checks, credits |
| 2D: **Art** | Your sprites, icons and tiles enlarged, including the ones the game still draws in code |
| 2D: **Pictures** | AI pictures from a description: concept art, references for sprites, icons, textures; cut-outs |
| 3D: **Models** | Work in progress, nothing works yet: will turn pictures into 3D models later |
| Audio: **Sounds** | Sound effects: AI sounds from a description, the retro sfxr generator, or a downloaded file |
| Audio: **Music** | Music: AI music from a description, your game's own music rendered by Godot, or a downloaded file |
| Audio: **Voices** | AI voice-overs: words read in a voice you describe |

The AI parts (pictures, music, AI sounds, voices) run on **your own graphics card**: no account, no limits,
nothing sent to the internet. See [AI engines](#ai-engines-how-they-work) below.

## Open it on a game

The page always works on one game: the one whose folder you start it from. That folder must have an
`assets.yaml` (a game without one: ask Claude to plan its assets first, or run `gamekit.py init` there).

**First time: make a double-click launcher (once per game)**

1. Open PowerShell.
2. Go to the game's folder, for example GameTest:
   ```
   cd C:\Repos\GameTest
   ```
3. Make the launcher:
   ```
   python C:\Repos\gamekit\plugins\gamekit\scripts\gamekit.py ui --launcher
   ```
   This only writes a file called `Start Gamekit.bat` into the game folder; it doesn't open the page.

**Every time after that:** double-click `Start Gamekit.bat` in the game's folder (in File Explorer).

**Without a launcher:** steps 1 and 2, then
```
python C:\Repos\gamekit\plugins\gamekit\scripts\gamekit.py ui
```

Either way a black window appears and the page opens in its own window (Brave, Chrome or Edge).
**Leave the black window open** while you use the page; close it (or press Ctrl+C in it) to quit.
After gamekit is updated, close the black window and start the page again to get the new version (the
version is shown next to the gamekit name at the top).

The `.bat` is just a shortcut: commit it with the game, or add it to `.gitignore` (GameTest does).
If gamekit's folder ever moves, run step 3 again.

If Claude or you edit `assets.yaml` while the page is open, press **Refresh** (top right).
**Folder** opens the game folder in File Explorer.

## Words you'll see

| Word | Meaning |
|---|---|
| **todo** | Not made yet (or the game still uses its old placeholder). |
| **draft** | A file exists but isn't final. Making a file on the page moves an asset to draft by itself. |
| **done** | You're happy with it in the game. Only you set this. |
| **source** | Where the asset comes from: `claude` (Claude draws it), `ai` (made by an AI engine on your PC), `sfxr` (the retro sound generator), `synth` (your game's own music code), `pack` / `library` (downloaded), `self` (you make it in Aseprite). |
| **take** | One try. You make a few takes, listen or look, and keep the best. Takes are scratch files: only the one you **use** becomes part of the game. |
| **seed** | The number that picks one particular take. The same settings and seed make the same take again. |
| **engine** | One AI model set up on your PC (pictures, music, sounds, voices). |

The **todo / draft / done** buttons under every asset change its status straight away.

## AI engines: how they work

**Setting up (once per engine, per PC):** a tab whose engine isn't set up shows a **Set up** button. It installs
what the model needs for your graphics card (a few GB, several minutes); the bar at the top shows progress.
On your PC the four big ones are already set up; the small cut-out engine sets itself up the first time you
press **Cut out (set up)** on the Pictures tab (about 300 MB, a minute).

**Making things:** press **Make it**. The bar at the top shows what's happening and how long it's taken, with a
**Stop** button. The first time you use an engine after starting the page it loads its model (30 to 50 seconds);
after that it's quick, as long as you stay with that engine.

**One at a time:** the engines share your graphics card, so only one is loaded at once. Switching from, say,
pictures to music unloads the picture model, and the next picture loads it again. Make a batch of one kind,
then move on. While one job runs, other AI buttons say "still busy". The cut-out engine is the exception: it runs on
the processor, so it doesn't unload the picture model.

**Every take has the same buttons:**

| Button | Does |
|---|---|
| **Keep** | Stars it, so you can find your favourites |
| **Another take** | Same settings, new seed: a new version |
| **Adjust** | Puts its settings back in the form, to change something and make it again |
| **Use as asset… / Use for a track…** | Makes it the game's file for an asset you pick, and marks that asset `source: ai` and draft |
| **Remove** | Moves it to the `_removed` folder next to it (not deleted) |

**Where things go:** takes are saved in the game folder, each with a `.json` beside it holding the settings
that made it: `pictures/`, `music-takes/`, `sound-takes/`, `voice-takes/`. GameTest's `.gitignore` keeps them out
of git. The engines and models themselves live in `%LOCALAPPDATA%\gamekit\engines` (about 50 GB in all), not in
the game or in gamekit.

**Speed on your PC (AMD RX 7800 XT):**

| Engine | Loading | Then |
|---|---|---|
| Pictures | ~30 s | ~30 s for a new description, ~8 s for more takes of it |
| Music | ~40 s | ~1.5 s per second of music (a 30-second track in ~50 s) |
| Sounds | ~45 s | well under a second a sound |
| Voices | ~35 s | a few seconds for a short line, ~20 s for a long one |
| Cut-outs | ~5 s | ~8 s a picture (on the processor) |

**Licences:** everything they make is yours to use, also in games you sell. Pictures (FLUX.2 klein) and voices
(Qwen3-TTS) are Apache 2.0, music (ACE-Step) and cut-outs (BiRefNet) are MIT. Sound effects (Stable Audio 3) use Stability AI's Community
License: free while you earn under $1M a year from what you make with it.

**Claude can't hear or see the way you do:** it checks takes by numbers (length, loudness, shape) and can look at
pictures, but whether a sound or tune is right is your call. Listen before you use a take.

## Assets tab: what's left

- **Progress** (left): how much is done, and a table per kind (sprites, icons, sounds, voices, music...).
- **Show**: filter by kind or status, or search. "Not done" hides finished things: a handy to-do list.
- The list (right): every asset with a small preview or a player, its size and animation frames, and notes.
- **Checks**:
  - **Check the manifest**: finds mistakes in `assets.yaml` (typos, missing sizes, missing licenses).
  - **Check the files**: checks made files are the right size, use the palette's colors, and that sounds aren't silent or distorted.
  - **Write CREDITS.md**: lists who made the downloaded assets, and what was made in-house or with AI. Ship it with the game.

## Sounds tab: make and pick sound effects

Pick the sound effect at the top left (e.g. `sfx_shoot`); its current sound, if any, plays below. Then make a new
one in any of three ways.

### Make a sound with AI

Realistic sounds from a description (Stable Audio 3). Its license is already accepted and the model is set up
on your PC. (On another PC: accept it once at https://huggingface.co/stabilityai/stable-audio-3-small-sfx, then
ask Claude to set the model up.)

1. **Describe the sound**: what makes it and where, e.g. "a heavy wooden door slams shut in a stone hall". The
   word buttons add things like *heavy*, *distant*, *metallic*, *in a cave*.
2. **Seconds** (0.5 to 30), **Takes**, and:
   - **Mono** (on): for sounds that come from a place in the game world. Off keeps stereo.
   - **Seamless loop**: for backgrounds that repeat, like fire, wind and rain.
3. **Make it**, then listen under **AI sounds** (right).
4. **Use as asset…** on the one you like: it becomes the game's sound, cleaned like an imported sound (mono,
   trimmed unless it's a loop, the game's level), and the asset becomes `source: ai`.

### Retro sounds (sfxr)

1. Pick a preset that's close to what you want (`hit`, `laser`, `explosion`, `pickup`, `jump`, `blip`,
   `powerup`, or `random`), set how many takes, and press **Make takes**.
2. **Listen** to the takes under **Retro takes** (right). Each one shows its length, loudness and a little shape
   (tall at the start = punchy, long tail = rings out).
3. **Change one you almost like** with the buttons under it. Each makes a new take:

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
4. **Keep this one** makes that take the game's sound (it writes the WAV the game loads) and moves the asset to
   draft. Then play the game and judge it there.
5. **Clear takes** deletes the retro takes when you're done choosing (they're scratch files in `sounds/variants/`).

**Takes similar to the current sound** works once a sound has been kept: small changes to it.

### Using a downloaded sound instead

1. Drop the file (`.wav`, `.mp3`, `.ogg`, `.flac`) on **Or import a sound file**, or click it to choose.
2. Options: **Trim silence** (leave on unless the sound starts quietly on purpose), **Cut to at most**
   (shortens a long sound with a fade), and **Match the loudness of**: drop the sound it replaces there
   so the new one is just as loud.
3. Press **Import**. It becomes a clean game-ready WAV. If the asset already has a file, you're asked first.
4. Downloaded sounds need their license written down. Tell Claude where it came from; never guess a license.

## Music tab: play, make, render and import music

- **Every track** (right) has a player. Looping tracks loop.
- Pick a track at the top left to see its numbers:
  - **LUFS**: how loud it feels. Tracks should be about the same (your game uses -16).
  - **true peak**: should stay below 0, or it distorts.
  - **loop jump** and **silence across it**: whether the loop point clicks or pauses. A small jump
    (close to the "normal" number) and almost no silence means a clean loop.

### Make music with AI

Music from a description (ACE-Step 1.5), on your graphics card.

1. **Describe the music**: instruments, mood, place. The mood buttons (dungeon, battle, boss, town, sad, menu)
   add common words; **loopable** asks for no intro and no ending.
2. Set the **Length**, and optionally **Tempo** and **Key** (empty = the model chooses), and how many **Takes**.
3. **Make it**, then listen under **AI takes** (right).
4. **Use for a track…**: pick the game's track it replaces, and **Start** / **End** (seconds) for the loop.
   It's made into the track's looping OGG at the game's loudness and marked `source: ai`.
5. Check the track's numbers on the left. AI music often fades out at the end, which shows up as
   **silence across the loop**: listen for where the fade starts, set **End** just before it, and use it again.

Under **Lyrics, planner, seed**: lyrics make it sing (empty = instrumental); the **planner** plans the song
first for better structure, but takes about 7 minutes a take on your AMD card and sometimes fails.

### Your game's own music, or a downloaded file

- **Render this track / Render every synth track** runs your game's own music code through Godot
  and saves the OGG files the game plays. Takes a minute or more.
- **Import a music file**: drop a file, optionally set **Start** and **End** (in seconds) to pick the
  part that loops, and press **Import**. It's converted to OGG at the game's loudness.
  **Keep its own loudness** skips that. Needs ffmpeg (already installed on your PC).

## Art tab: look at your sprites

- A gallery of every image, enlarged with crisp pixels. Use **Zoom** to change the size.
- Empty dashed boxes are images not made yet; the box shows the size the game expects.
- **from code**: images with no art file yet that the game draws itself from text in its code
  (GameTest: `src/art/pixel_art.gd`, set as `code_art` in `assets.yaml`). That's what the player sees
  today. Magenta parts are the player color. Once an art file exists, the page shows the file instead,
  just like the game. **Only finished art files** hides the code art.
- Animated sprites show all their frames together.
- **Draw** (for `claude` assets): Claude writes each sprite as text in `art/<id>.yaml`. To get a new or
  changed sprite, ask Claude (e.g. "draw the bat"). If you edit the text file yourself, press
  **Draw** to turn it into the PNG.
- **Export** (for `self` assets): turns your Aseprite file into the PNG. Needs Aseprite.
- **Check** / **Check the images**: size and palette problems, listed at the top.

## Pictures tab: AI pictures

Pictures from a description (FLUX.2 klein), on your graphics card.

1. **Describe the picture** in the box. Style first, then the subject: "pixel art sprite of a hooded cultist
   holding a candle, dark fantasy, full body, plain white background".
2. The **style buttons** add common endings (pixel art sprite, item icon, seamless texture, character sheet,
   concept art, dark fantasy). FLUX.2 klein draws good pixel art on its own with the **pixel art sprite** words.
3. **Size**: 768 is faster. **Takes**: how many versions. **Repeats without a seam** for floor and wall textures.
   **Seed**: leave empty for new versions.
4. **Make it**. Click any picture to see it full size.

Besides the usual take buttons, pictures have **Work from this**: the next pictures start from that one, so you
can describe "the same character seen from behind" and get a matching back view.

**Cut out** makes a copy of a picture with the background made transparent by a second AI model (BiRefNet),
shown on a checkerboard and marked "cut-out". It keeps soft edges, hair and gaps between arms and body, which the
simple background removal under **Use as asset…** can miss, and it works on busy backgrounds too. Use the cut-out
as the asset (its transparency is kept as it is).

**Use as asset…** turns a picture into one of the game's images: the background removed (**Remove the
background**), shrunk to the asset's size, and the colors snapped to the palette (**Snap to the palette**).
Animated sprites can't be made this way (a picture is one frame).

**Tip for pixel art:** shrinking a big picture to a tiny sprite (16×16 and smaller) loses most of the detail,
and snapping to the palette can pick colors with a special meaning (in GameTest, magenta is the player color).
For small sprites, use the picture as a reference and ask Claude to draw the sprite from it. Shrinking works
well for textures and bigger images.

## Voices tab: AI voice-overs

Spoken lines (Qwen3-TTS), on your graphics card.

1. **Words to say**: only the words. Up to 1,500 characters a reading; split anything longer.
2. **Voice: who is speaking**: age, man or woman, the sound of the voice, accent, pace. The buttons (narrator,
   innkeeper, villain, hero, creature, child) fill in a voice and a tone to start from.
3. **Tone or scene: how it's said**: whispering, shouting across a field, weary, amused.
4. **Language**, **Takes**, and **Make it**. Listen under **Readings** (right).

Each take is a different reading; keep the best. The same Voice text gives a *similar* voice, not an identical
one: for a character with many lines, copy a good take's seed into **Seed** and keep the Voice text exactly the
same.

**Use as asset…** makes a reading the game's sound for a `voice` asset (or a sound effect). Voice lines need
entries in `assets.yaml` with `kind: voice`: ask Claude to add the ones your game needs.

## A typical session

1. Open the page and go to **Assets**. Set Status to **Not done** to see what's left.
2. **Sounds**: pick a sound, make AI or retro takes, listen, and use or keep the best.
3. **Music**: describe a track, make two or three takes, use the best for its track and fix the loop end.
4. **Voices**: write the lines, pick a voice, keep the best readings and use them.
5. **Pictures**: make references or textures; for small sprites, ask Claude to draw them from your favourite picture.
6. Play the game. Happy with something? Mark the asset **done**.
7. Before a release: **Check the manifest**, **Check the files**, and **Write CREDITS.md**.

## When something goes wrong

| Problem | Fix |
|---|---|
| `gamekit` is not recognized | Use the full command: `python C:\Repos\gamekit\plugins\gamekit\scripts\gamekit.py ui` |
| "not found. Run `gamekit init` first" | Run it from the game folder (the one with `assets.yaml`). |
| The window doesn't open | Open the address printed in the black window (`http://127.0.0.1:7862`) in any browser. |
| "no answer from gamekit" | The black window was closed. Start it again. |
| "still busy" | Another job (an AI take, music rendering) is running. Wait, or press **Stop** in the bar. |
| Changes made by Claude don't show | Press **Refresh**. |
| A new tab or button is missing after an update | Close the black window and start the page again. |
| "the … engine isn't set up yet" | Press **Set up** on that tab (once per PC). |
| "the … model stopped unexpectedly" | Close games and other programs that use the graphics card, then try again. If it keeps happening, the log it names (in `%LOCALAPPDATA%\gamekit\engines\logs`) says why: show it to Claude. |
| The sound model "is locked" | Its license hasn't been accepted on this PC's account: see [Make a sound with AI](#make-a-sound-with-ai). |
| The first AI take is slow | Normal: the engine loads its model first (30 to 50 seconds). |
| A player shows the wrong length | The browser guesses until the track has loaded; press play. |
