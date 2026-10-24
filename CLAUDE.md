# CLAUDE.md

Gamekit is a Claude Code plugin (plus plain Python CLI) for a game's art and audio pipeline. The
owner is new to game dev and has Claude write most of the code: explain new concepts briefly and
prefer simple, readable solutions. Users (Godot games, Windows): Medieval Survival
(`Tristan2828/medieval-survival`, formerly GameTest; local folder `C:\Repos\medieval-survival`) and
`C:\Repos\vertical-scroller` (the Packs tab was built for its downloads).

## Layout
- `.claude-plugin/marketplace.json`: makes this repo installable (`/plugin marketplace add Tristan2828/gamekit`).
- `plugins/gamekit/`: the plugin itself. No `CLAUDE.md` in there (plugins don't load one; put
  instructions for Claude in skills).
  - `.claude-plugin/plugin.json`: manifest. Bump `version` when releasing changes (users stay pinned to it).
  - `skills/<name>/SKILL.md`: one per workflow. Reference bundled files as `${CLAUDE_PLUGIN_ROOT}/...`
    (substituted when the skill loads; it is NOT an environment variable in Bash).
  - `scripts/gamekit.py`: CLI entry; logic in `scripts/gamekit_lib/` (one module per concern).
  - `ui/index.html`: the asset page (`gamekit ui`), served by `gamekit_lib/ui.py` (stdlib `http.server`,
    127.0.0.1 only). One file, no build step or JS libraries; new tabs = a section there + a route in `ui.py`.
  - `engines/<name>_worker.py`: local AI model workers, run in their own Python (`gamekit_lib/engines.py`
    sets those up under %LOCALAPPDATA%\gamekit\engines and talks to them: JSON lines, `@@` prefix).
    The owner's GPU is an AMD RX 7800 XT (ROCm on Windows, Python 3.12); keep CUDA-only add-ons out.
  - `templates/`: files `gamekit init` copies into a game, plus `godot/render_music.gd` for `music render`.
- `tests/`: `unittest` tests (no pytest needed).

## Rules
- The asset manifest (`assets.yaml`) is the single source of truth; every tool reads it and the
  field reference lives in `templates/assets.yaml`'s header comment. Keep that comment, the
  validator (`manifest.py`) and the skills in sync when adding a field, kind or source.
- Scripts must run on Windows (the owner's PC) and Linux (cloud sessions): `pathlib`, UTF-8 reads
  and writes, no shell-specific tricks, plain ASCII console output.
- Keep dependencies few and listed in `plugins/gamekit/requirements.txt`. External programs
  (Aseprite, ffmpeg, Godot) are found via PATH or a configurable path, with a clear error if missing.
- Never guess a license. Assets from packs, libraries or commissions need license name + author.
- Typed Python (annotations on functions), standard library first.

## Pictures pipeline (how the pieces fit)
User guide: `docs/asset-page.md`. Logic: `pictures.py` (library, shrinking), `touchup.py` (drafts), `ui.py` routes.
- `pictures/` in the game holds every AI picture: `<name>.png` + `<name>.json` meta. Meta keys: `prompt`, `seed`,
  `width`/`height`, `for` (asset id), `frame`, `refs` (worked from), `kept` (starred), `tile`, `cutout_of`,
  `sprite_of` (a game-sized **sprite tile**), `touchup` (a **touch-up draft**), `copy_of`, `pack`/`pack_file`/`box`
  (copied from a pack: Use makes the asset `source: pack`), `packs` (AI art worked from pack art). Remove moves files
  (incl. a draft's `.yaml`) to `pictures/_removed`; nothing is deleted.
- Only an explicit **Use** writes into the game (`picture-use`, `picture-frames`, the page's Use buttons). Touch-up
  never does: `touchup` makes `pictures/<stem>-touchup-<w>x<h>.png` + `.yaml` text rows; Claude edits the yaml and
  runs `touchup-render`; the user presses Use. (The owner explicitly asked for this; don't make tools write the game.)
- Sprite tiles are already game-sized: `make_sprite`/`make_frames` pass them through unchanged. `make_frames` uses
  one shared crop for all frames (no jitter) and refuses mixed sizes, so picture animations exclude sprite tiles.
- Animate panel: from a picture, empty frames are made by FLUX from it (`refs`); from a sprite tile (`anim.sprite`)
  the frames are too small for AI, so "Animate with Claude" makes drafts for every frame (`--every-frame`) and the
  user asks Claude to "animate the <id> drafts" (see the art-draw skill).
- "Work from this" = FLUX reference images: the new picture keeps the creature's look; the words say only what changes.
- Packs tab (`packs.py`): downloads sit in the game's `packs/` (zip/rar/7z/folder; `_` names ignored), Import makes
  `packs/<name>/files/` + `pack.yaml` (license, `download`, `starred`). Nothing leaves an unlicensed pack. A boxed part
  is used directly (`to_sprite`: same size pixel for pixel, else fitted using the whole box) or copied to `pictures/`
  enlarged on white (`to_picture`; the picture engine drops transparency to black).

## Working with the owner
- They test on the page and give UI feedback in batches; explain choices briefly (e.g. why two similar buttons exist).
- Release flow when they say so: run tests, bump `plugin.json` version, commit, **ask before `git push`**, then
  `claude plugin marketplace update gamekit` + `claude plugin update gamekit@gamekit`, and restart the page from
  `C:\Repos\medieval-survival` (`python C:\Repos\gamekit\plugins\gamekit\scripts\gamekit.py -m assets.yaml ui`, port 7862).
  Claude Code itself must be restarted to load new skills.
- Visual checks of the page: Playwright MCP works (Chrome MCP screenshots time out on a throttled window). Delete the
  `.playwright-mcp/` folder it leaves in the repo before committing. Try destructive CLI commands on a scratch copy
  of GameTest, not the real game.
- On Windows, write multi-line edit scripts to a scratch `.py` file rather than a shell heredoc with backslashes.

## Verify
- `python -m unittest discover -s tests` (use `python3` on Linux).
- `claude plugin validate .` when the CLI is available.
