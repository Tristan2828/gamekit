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
2. Go to the game's folder, for example medieval-survival:
   ```
   cd C:\Repos\medieval-survival
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

The `.bat` is just a shortcut: commit it with the game, or add it to `.gitignore` (Medieval Survival does).
If gamekit's folder ever moves, run step 3 again.

If Claude or you edit `assets.yaml` while the page is open, press **Refresh** (top right).
**Folder** opens the game folder in File Explorer.

## Words you'll see

| Word | Meaning |
|---|---|
| **todo** | Not made yet (or the game still uses its old placeholder). |
| **draft** | A file exists but isn't final. Making a file on the page moves an asset to draft by itself. |
| **done** | You're happy with it in the game. Only you set this. |
| **keep** | The game keeps its own version (the sprite or sound its code makes), because you chose it. Counts as finished; no file needed. |
| **source** | Where the asset comes from: `claude` (Claude draws it), `ai` (made by an AI engine on your PC), `sfxr` (the retro sound generator), `synth` (your game's own music code), `pack` / `library` (downloaded), `self` (you make it in Aseprite). |
| **take** | One try. You make a few takes, listen or look, and keep the best. Takes are scratch files: only the one you **use** becomes part of the game. |
| **seed** | The number that picks one particular take. The same settings and seed make the same take again. |
| **engine** | One AI model set up on your PC (pictures, music, sounds, voices). |

The **todo / draft / done / keep** buttons under every asset change its status straight away. Click several quickly
if you like: each one waits for the one before it.

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
| **Keep** (a star on pictures) | Stars it, so you can find your favourites (Pictures: **Show: ★ Starred**) |
| **Another take** | Same settings, new seed: one more version, right away |
| **Adjust** (pictures: **edit and make again**, a pencil) | Puts its settings, seed included, back in the form, to change something first and make it again |
| **Use as asset… / Use for a track…** | Opens a box under it: pick the asset (it starts on *(pick one)*), then **Use**. Makes it the game's file for that asset, and marks it `source: ai` and draft. If the asset already has a file, you're asked first, with its name |
| **Remove** (red) | Moves it to the `_removed` folder next to it (not deleted). Starred or kept ones ask first |

On the Pictures tab most of these are small icon buttons: hover over one to see its name.

**Where things go:** takes are saved in the game folder, each with a `.json` beside it holding the settings
that made it: `pictures/`, `music-takes/`, `sound-takes/`, `voice-takes/`. Medieval Survival's `.gitignore` keeps them out
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
- The list (right): every asset with a small preview or a player, its size and animation frames, and notes (click
  them to read all of it). **Work on this →** opens the tab where it's made, with it picked: Sounds or Music with that
  sound or track chosen, Voices, Pictures with **For asset** set (for `ai` sprites), or Art showing just that image.
- **Checks**:
  - **Check the manifest**: finds mistakes in `assets.yaml` (typos, missing sizes, missing licenses).
  - **Check the files**: checks made files are the right size, use the palette's colors, and that sounds aren't silent or distorted.
  - **Write CREDITS.md**: lists who made the downloaded assets, and what was made in-house or with AI. Ship it with the game.
  - In the results, an asset's name is a link: click it to show just that asset in the list.

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

- A gallery of every image, enlarged with crisp pixels. Use **Zoom** to change the size, **Search** to find one by name.
- Empty dashed boxes are images not made yet; the box shows the size the game expects.
- **from code**: images with no art file yet that the game draws itself from text in its code
  (Medieval Survival: `src/art/pixel_art.gd`, set as `code_art` in `assets.yaml`). That's what the player sees
  today. Magenta parts are the player color. Once an art file exists, the page shows the file instead,
  just like the game. **Only finished art files** hides the code art.
- Animated sprites show all their frames together.
- **Claude's drafts** (for `claude` assets): Claude writes each sprite as text in `art/<id>.yaml`, which the
  game doesn't read. Ask for a batch, e.g. "redraw the relic icons": Claude starts each draft from the game's
  own drawing (`gamekit seed`) and improves it. A tile with a draft waiting has a yellow border and shows
  **now** next to **Claude's draft**. **Only Claude's drafts waiting for you** shows just those.
  - **Use draft** puts that draft into the game (todo becomes draft). **Use all drafts shown** does every
    waiting tile on screen, after asking once. Don't like one? Tell Claude what to change, or leave it.
  - **Draw** (no draft waiting): draws the text file into the game again, e.g. after you edited it yourself.
- **Export** (for `self` assets): turns your Aseprite file into the PNG. Needs Aseprite.
- **Check** / **Check the images**: size and palette problems, listed at the top.

## Pictures tab: AI pictures

Pictures from a description (FLUX.2 klein), on your graphics card.

1. **For asset** (optional): pick the sprite the picture is for, e.g. *shambler (12×12, 3 frames)*. It writes
   the description for you, from the asset's size ("a 12x12 pixel art sprite, each pixel a clean square block"),
   the game's sprite rules and the asset's notes in `assets.yaml`. It also sets **Size** to the asset's own shape
   ("Same shape as bat (14×8): 1360×768"),
   and names the pictures after the asset (`shambler-31.png`). Change the words as you like.
2. Or **describe the picture** yourself. Style first, then the subject. The **style buttons** add common endings
   (pixel art sprite, item icon, seamless texture, character sheet, concept art, dark fantasy).
3. **Size**: square, wide and tall shapes; smaller is faster (512 the fastest). **Takes**: how many versions. **Repeats without a seam** for floor and wall textures.
   **Seed**: leave empty for new versions.
4. **Make it**. Click any picture (or press Enter on it) to see it full size; click again or press Escape to close.

**Each picture tile** shows the asset it's for and the words that matter, with tags under them (sprite and its
size, cut-out, touch-up draft, worked from a picture). **Details** shows the whole description, size, seed, date
and file name. On the picture: a **star** for your favourites and a **Picture / In game** switch. Under it,
**Use as asset…**, then small icon buttons (hover for their names): cut out (scissors), **another take** (one
more right away: same words and size, new seed), **edit and make again** (pencil: puts its words, size and seed in
the form so you can change something first; with the same seed, a small change in the words gives a close
variation), work from this, animate (a walking person), and **remove** (red, on the right; it moves the picture to
`pictures/_removed`, and asks first if it's starred). Sprite tiles have **Use in game…**, **Touch up with Claude** and animate. Above the tiles, **Show** picks All, **★ Starred** or
**Sprites** (sprite tiles and touch-up drafts), and **View** shows every tile as a picture or in game.

**Work from this** starts the next pictures from that one: the new pictures keep the creature's look, colors and
size. The tile gets a green frame, the form scrolls into view with the picture under **Working from**, the size and
asset are set to match, and the description starts with "the same creature, same colors and style, ": add only
what changes (a pose, a view, something it holds), or press a pose (**walk 1**, **walk 2**, **attack**...). Press
it again, or × under Working from, to stop.

**Animate…** turns a picture into a whole animation for an animated sprite:
1. Press **Animate…** under the picture. A panel opens at the top with one box per frame of the asset (e.g.
   `shambler`, `shambler_walk_1`, `shambler_walk_2`). The first frame uses your picture (its cut-out if it has one).
   A picture that wasn't made for an animated sprite asks which one first.
2. Empty frames show the words they'll be made from ("...walking, left foot forward"). Change them if you like,
   then press **Make the missing frames**. Each one is made from your picture, then cut out (about 30 s each,
   plus loading the model the first time).
3. The players at the bottom **play each animation** (idle, walk, attack) twice: zoomed in, to see every pixel,
   and **in game**: at the size the game shows it (3× on a 1080p screen) on the floor color you pick under
   **Floor**. Use the **Speed** slider. Don't like a frame? Pick another picture in its box, or choose "(none yet: make it)" and make
   it again.
4. **Use all frames** saves every frame file at once. They're all shrunk with **the same crop**, so the creature
   stays in place and keeps its size from frame to frame (shrinking them one at a time would make it jitter).

**Animating a sprite** (the walking person on a sprite tile) opens the same panel with game-sized sprites in the
frames. They're too small for the AI to draw new frames, so **Animate with Claude** adds a draft of every frame to
your pictures (empty frames start as a copy of the one before), and you ask Claude to **animate the bone_warden
drafts**. The panel then plays the drafts; when they look right, **Use all frames**.

**In game** on a picture switches it to the sprite it would become (shrunk, outlined, on the palette) at the size
the game shows it, on your floor color; **Picture** switches back. **View: In game** above the list switches them
all. It uses the asset the picture was made for (For asset, Animate), or the one you pick under **Use as asset…**.
Nothing is saved.

**Keep as a sprite tile** (under **Use as asset…**) keeps the game-sized sprite as a new tile in your pictures, marked
"Sprite for shambler" and shown pixel-sharp. Make a few from different pictures and compare them side by side,
with **In game** too. A sprite tile can be used as the asset as it is, or touched up.

**Touch up with Claude** (under **Use as asset…**, and in the Animate panel for all frames at once) is for small
sprites, where shrinking loses the face, eyes or outline. It adds a **touch-up draft** tile to your pictures
(one per frame from the Animate panel; frames without a picture start as a copy of the one before), with its
pixels saved as text beside it. Nothing goes into the game. Then tell Claude **"touch up the shambler drafts"**:
it looks at the drafts and the big pictures, fixes the pixels by hand (centering, outline, eyes, silhouette, and
the walk frames' movement), and the tiles update. Press **Use** on a draft when you like it.

**Cut out** makes a copy of a picture with the background made transparent by a second AI model (BiRefNet),
shown on a checkerboard and marked "cut-out". It keeps soft edges and the gaps between arms and body, which the
simple background removal can miss. Cut out before you use a picture as a sprite.

**Use as asset…** opens the tile across the whole row, with the picture on the left and three steps on the right:
- Pick **which sprite** and, for animated sprites, **which frame** (`shambler`, `shambler_walk_1`, `shambler_walk_2`).
  Each frame is its own file, so use one picture per frame. A picture made for a sprite starts on it; any other starts
  on *(pick one)*, and nothing can be used until you pick.
- **Shrinking**: **Remove background**, **Snap to palette** (never to the reserved player colors) and
  **Outline** follow the game's sprite rules; switch any of them off.
- **What it makes** shows exactly what will be saved, zoomed in and in game. Change the options and it updates
  ("Making the preview…" while it works: a few seconds for a big picture).
- Then **Use in game** (replaces the sprite in your game), **Keep as a sprite tile**, or **Touch up with Claude**.
  Only **Use in game** changes the game.

How shrinking works: each sprite pixel takes the most common palette color in its patch of the picture, matched
by hue. So small details such as red eyes keep their color instead of turning into a brown-grey average.

**What to expect at each size** (tried on Medieval Survival's enemies):
- **18×18 and bigger** (bosses, ghoul, paladin): good starting points, often usable after a quick touch-up.
- **10 to 14 px** (shambler, cultist, imp): readable blobs with the right colors and eyes. Fine as drafts.
- **Smaller or very wide** (bat 14×8, mire crawler 10×8): the face mostly disappears.
For the small ones, keep your favorite picture and ask Claude to draw the sprite from it: "draw the bat from
`pictures/bat-31.png`". Claude can look at the picture, and drawing by hand at 8 px beats any shrink.

**The game's sprite rules** live at the top of `assets.yaml`:

```yaml
sprites:
  prompt: "chunky, chibi proportions, oversized head, big glowing eyes, dark fantasy, ..."
  outline: "#17121C"                       # 1 px outline drawn around every sprite
  reserved_colors: ["#FF00FF", "#800080"]  # player colors: never snapped to
  game_scale: 3                            # how much the game enlarges sprites (for "in game" previews)
  floors: {The Crypt: "#1C1A21", ...}      # floor colors to preview sprites on
```

## Packs tab: downloaded asset packs

Ready-made art you downloaded (itch.io, Kenney, OpenGameArt...), to browse, shortlist, use, or make new AI art from.

**1. Put downloads in the game's `packs/` folder.** A `.zip`, `.rar`, `.7z` or a plain folder. They show under
**New downloads**. Press **Import**: the pack is copied to `packs/<name>/files/`, with a `packs/<name>/pack.yaml`
beside it. The download itself stays where it is. Folders whose names start with `_` are ignored (your own notes,
previews...). `.rar` and `.7z` are opened with 7-Zip if it's installed, otherwise with Windows' own `tar`.

**2. Record the license.** Click the pack's name under **Packs**. It lists the pack's license and readme files (click
one to read it; PDFs open in the browser). The words in brackets are hints found in those files, not the answer. Fill in
**License** (e.g. CC0, CC-BY 4.0) and **Credit** (who made it), then **Save license**. Or ask Claude: "record the
license of the foozle pack". Until a pack has a license, you can look at it and star images, but nothing can be taken from it.
The pill shows what it means: **CC0** (free, no credit needed), another license (check what it asks, usually a credit in
`CREDITS.md`), or **license not set**.

**3. Browse and shortlist.** Every image of every pack is on the right. Filter by pack or search by file name; **★**
puts an image on the shortlist (saved in `pack.yaml`), and **Only the shortlist** shows just those.

**4. Box a part of an image.** Click an image. Drag on it to draw a box (or type x, y, width, height). **Trim** shrinks
the box to the visible pixels inside it. For sprite sheets, turn on **Grid** with the sheet's frame size: then a click
picks one cell. Then:
- **Use in game**: pick the sprite (and frame). A box the sprite's own size is used pixel for pixel; any other size is
  fitted, keeping its shape. **Snap to palette** recolors it to your palette. The asset becomes `source: pack` with the
  pack's license, so credits stay right.
- **Next frame →**: for animations in a row. Moves the box one box along and picks the next frame; press **Use in game**
  for each.
- **Copy to Pictures**: the boxed part goes to your pictures (enlarged, on white), tagged **from pack**. There,
  **Work from this** makes new AI pictures in its style, **Use as asset…** and **Touch up with Claude** work as for any
  picture. Nothing goes into the game.

AI pictures made from pack art are tagged **from pack art**. When one is used in the game, the message names any pack
whose license isn't CC0, so you can check that it allows this and credit it if it asks.

**Git:** commit each `packs/<name>/pack.yaml` (the licenses), ignore the rest. In `.gitignore`:

```
packs/*
!packs/*/
packs/*/*
!packs/*/pack.yaml
```

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
5. **Art**: ask Claude to redraw a family of icons or sprites; look at its drafts next to what the game has now and
   **Use** the ones you like. **Pictures**: make references or textures; for small sprites, ask Claude to draw them
   from your favourite picture.
6. Play the game. Happy with something? Mark the asset **done**. Decided the game's own version stays? Mark it **keep**.
7. Before a release: **Check the manifest**, **Check the files**, and **Write CREDITS.md**.

**Keyboard:** Tab moves between everything you can press (a green ring shows where you are); Enter or Space presses
it, including pictures, pack images and pack names; Escape closes a picture shown full size.

## When something goes wrong

| Problem | Fix |
|---|---|
| `gamekit` is not recognized | Use the full command: `python C:\Repos\gamekit\plugins\gamekit\scripts\gamekit.py ui` |
| "not found. Run `gamekit init` first" | Run it from the game folder (the one with `assets.yaml`). |
| The window doesn't open | Open the address printed in the black window (`http://127.0.0.1:7862`) in any browser. |
| "no answer from gamekit" | The black window was closed. Start it again. |
| "still busy" | Another job (an AI take, music rendering) is running. Wait, or press **Stop** in the bar. (Quick clicks, like several status buttons, just wait their turn.) |
| Changes made by Claude don't show | Press **Refresh**. |
| A new tab or button is missing after an update | Close the black window and start the page again. |
| "the … engine isn't set up yet" | Press **Set up** on that tab (once per PC). |
| "the … model stopped unexpectedly" | Close games and other programs that use the graphics card, then try again. If it keeps happening, the log it names (in `%LOCALAPPDATA%\gamekit\engines\logs`) says why: show it to Claude. |
| The sound model "is locked" | Its license hasn't been accepted on this PC's account: see [Make a sound with AI](#make-a-sound-with-ai). |
| The first AI take is slow | Normal: the engine loads its model first (30 to 50 seconds). |
| A player shows the wrong length | The browser guesses until the track has loaded; press play. |
