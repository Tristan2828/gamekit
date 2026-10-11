# CLAUDE.md

Gamekit is a Claude Code plugin (plus plain Python CLI) for a game's art and audio pipeline. The
owner is new to game dev and has Claude write most of the code: explain new concepts briefly and
prefer simple, readable solutions. First user: the Godot game `Tristan2828/GameTest` (Windows).

## Layout
- `.claude-plugin/marketplace.json`: makes this repo installable (`/plugin marketplace add Tristan2828/gamekit`).
- `plugins/gamekit/`: the plugin itself. No `CLAUDE.md` in there (plugins don't load one; put
  instructions for Claude in skills).
  - `.claude-plugin/plugin.json`: manifest. Bump `version` when releasing changes (users stay pinned to it).
  - `skills/<name>/SKILL.md`: one per workflow. Reference bundled files as `${CLAUDE_PLUGIN_ROOT}/...`
    (substituted when the skill loads; it is NOT an environment variable in Bash).
  - `scripts/gamekit.py`: CLI entry; logic in `scripts/gamekit_lib/` (one module per concern).
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

## Verify
- `python -m unittest discover -s tests` (use `python3` on Linux).
- `claude plugin validate .` when the CLI is available.
