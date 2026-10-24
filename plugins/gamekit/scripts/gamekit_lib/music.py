"""Music: render a game's own scores through Godot, or take any music file, and make looping OGGs.

Rendering: the game provides a Godot script (assets.yaml `music.render_script`) that writes
<out>/<track>.wav for each `--track=<name>` it's given:

    godot --headless --path <music.godot_project> -s <render_script> -- --out=<folder> --track=<name> ...

The track name is the asset's `replaces` (its name in the game) or its id. ffmpeg then encodes
each WAV to Ogg Vorbis. Music is not trimmed or faded (that would break the loop); loudness is
only changed when asked: one fixed gain for the whole track (EBU R128), plus a gentle peak limiter
when the loudest hits would otherwise clip; the loop stays seamless either way.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import audio

GODOT_GLOBS = [
    r"C:\Program Files\Godot*\Godot*console*.exe",
    r"C:\Godot*\Godot*console*.exe",
    r"C:\*\Godot\Godot*console*.exe",
    r"C:\Program Files (x86)\Steam\steamapps\common\Godot Engine\godot*.exe",
    os.path.expanduser(r"~\Godot*\Godot*console*.exe"),
    "/Applications/Godot*.app/Contents/MacOS/Godot",
]
SEAM_WINDOW_MS = 30.0


class MusicError(Exception):
    pass


def find_godot() -> str:
    configured = os.environ.get("GAMEKIT_GODOT")
    if configured:
        if Path(configured).exists():
            return configured
        raise MusicError(f"GAMEKIT_GODOT points to {configured}, which doesn't exist")
    for name in ("godot", "godot4", "Godot"):
        found = shutil.which(name)
        if found:
            return found
    for pattern in GODOT_GLOBS:
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[-1]
    raise MusicError("Godot not found. Set GAMEKIT_GODOT to the Godot executable "
                     "(on Windows the *_console.exe one) or add it to PATH.")


def render_command(godot: str, project: Path, script: str, out_dir: Path, tracks: list[str]) -> list[str]:
    return ([godot, "--headless", "--path", str(project), "-s", script, "--", f"--out={out_dir}"]
            + [f"--track={t}" for t in tracks])


def render_wavs(godot: str, project: Path, script: str, tracks: list[str], out_dir: Path) -> dict[str, Path]:
    """Runs the game's render script; returns track -> WAV path."""
    if not (project / "project.godot").exists():
        raise MusicError(f"no project.godot in {project} (set music.godot_project in assets.yaml)")
    if not (project / script).exists():
        raise MusicError(f"render script {project / script} not found (set music.render_script in assets.yaml)")
    result = subprocess.run(render_command(godot, project, script, out_dir, tracks),
                            stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    wavs = {t: out_dir / f"{t}.wav" for t in tracks}
    missing = [t for t, p in wavs.items() if not p.exists()]
    if result.returncode != 0 or missing:
        log = (result.stderr or result.stdout).strip()[-1500:]
        raise MusicError(f"Godot didn't render {', '.join(missing) or 'the tracks'} "
                         f"(exit code {result.returncode}):\n{log}")
    return wavs


# --- encoding ---------------------------------------------------------------------------------

def _cut_args(start: float | None, end: float | None) -> list[str]:
    args = []
    if start is not None:
        args += ["-ss", f"{start:.3f}"]
    if end is not None:
        args += ["-to", f"{end:.3f}"]
    return args


def measure_loudness(source: Path, ffmpeg: str | None = None, start: float | None = None,
                     end: float | None = None, filters: str = "") -> dict[str, float]:
    """EBU R128 numbers from ffmpeg's loudnorm analysis: integrated LUFS, true peak, range.
    `filters` are applied first, to measure what a filter chain would produce."""
    chain = (filters + "," if filters else "") + "loudnorm=print_format=json"
    command = ([ffmpeg or audio.find_ffmpeg(), "-hide_banner", "-nostats"] + _cut_args(start, end)
               + ["-i", str(source), "-af", chain, "-f", "null", "-"])
    result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace")
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", result.stderr)
    if result.returncode != 0 or not match:
        raise MusicError(f"ffmpeg couldn't measure {source}: {result.stderr.strip()[-500:]}")
    data = json.loads(match.group(0))
    return {k: float(data[k]) for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
            if data.get(k) not in (None, "-inf", "inf")}


PEAK_CEILING_DB = -1.5


def limiter(gain_db: float) -> str:
    """Gain, then a peak limiter at the ceiling (only the loudest hits are touched; no auto level)."""
    return (f"volume={gain_db:.2f}dB,"
            f"alimiter=limit={audio.db_to_gain(PEAK_CEILING_DB):.4f}:attack=5:release=50:level=disabled")


def loudness_filter(source: Path, target: float, ffmpeg: str, start: float | None = None,
                    end: float | None = None) -> tuple[str, str]:
    """The filter that brings `source` to `target` LUFS, and a note for the user.
    One fixed gain when the peaks allow it; otherwise gain plus a peak limiter, measured and
    corrected up to three times (the limiter takes a little loudness back)."""
    m = measure_loudness(source, ffmpeg, start, end)
    if "input_i" not in m:
        raise MusicError(f"{source} is silent")
    gain = target - m["input_i"]
    if gain <= PEAK_CEILING_DB - m.get("input_tp", -99.0):
        return f"volume={gain:.2f}dB", ""
    for _ in range(3):
        result = measure_loudness(source, ffmpeg, start, end, limiter(gain)).get("input_i", target)
        if abs(target - result) < 0.3:
            break
        gain += target - result
    over = gain - (PEAK_CEILING_DB - m.get("input_tp", -99.0))
    return limiter(gain), f"peaks limited by up to {over:.1f} dB to reach {target:g} LUFS"


def encode_ogg(source: Path, out: Path, loudness: float | None = None, quality: int = 5,
               start: float | None = None, end: float | None = None) -> str:
    """Any audio file -> Ogg Vorbis at 44100 Hz (channels kept). With `loudness` (LUFS, e.g. -16)
    the track is brought to that integrated loudness: one fixed gain, plus a peak limiter only
    when the peaks would pass -1.5 dB. Returns a note for the user (empty if nothing to say)."""
    ffmpeg = audio.find_ffmpeg()
    note = ""
    command = [ffmpeg, "-y", "-v", "error"] + _cut_args(start, end) + ["-i", str(source)]
    if loudness is not None:
        chain, note = loudness_filter(source, loudness, ffmpeg, start, end)
        command += ["-af", chain]
    out.parent.mkdir(parents=True, exist_ok=True)
    command += ["-ar", "44100", "-c:a", "libvorbis", "-q:a", str(quality), str(out)]
    result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise MusicError(f"ffmpeg couldn't encode {out.name}: {result.stderr.strip()[-500:]}")
    return note


# --- describing -------------------------------------------------------------------------------

@dataclass
class MusicInfo:
    seconds: float
    lufs: float | None
    true_peak: float | None
    seam_jump: float          # sample difference across the loop point (end -> start)
    edge_motion: float        # how much the waveform normally moves per sample near the ends
    silent_head: float        # seconds of near-silence at the start
    silent_tail: float        # ... and at the end: together, the pause when it loops
    exact: bool = True        # False: the decoded length is off, so the loop numbers can't be trusted


SILENCE_DB = -45.0            # relative to the track's peak
MAX_LOOP_GAP = 1.0            # seconds of silence across the loop point before it sounds like a stop


def describe(path: Path, loop_source: Path | None = None) -> MusicInfo:
    """Numbers for a music file. ffmpeg decodes some (mostly short) Ogg files a few samples too
    long or short, which would fake a click at the loop point; when the decoded length doesn't
    match the file's own sample count, the loop is measured on `loop_source` (the WAV it was
    made from) if given, else marked as not exact. Games (Godot included) play the exact length."""
    samples = audio.read(path)
    try:
        m = measure_loudness(path)
    except MusicError:
        m = {}
    expected = ogg_sample_count(path)
    exact = expected is None or expected == len(samples)
    seconds = (expected if expected else len(samples)) / audio.RATE
    loop_samples = samples
    if not exact and loop_source is not None and loop_source.exists():
        loop_samples, exact = audio.read(loop_source), True
    jump, motion = seam(loop_samples)
    head, tail = silent_ends(loop_samples)
    return MusicInfo(seconds, m.get("input_i"), m.get("input_tp"), jump, motion, head, tail, exact)


def ogg_sample_count(path: Path) -> int | None:
    """Total samples of a 44100 Hz Ogg Vorbis file: the granule position on its last page."""
    if path.suffix.lower() != ".ogg":
        return None
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 65536))
        tail = f.read()
    at = tail.rfind(b"OggS")
    if at < 0 or at + 14 > len(tail):
        return None
    granule = int.from_bytes(tail[at + 6: at + 14], "little", signed=True)
    return granule if granule > 0 else None


def seam(samples: list[float]) -> tuple[float, float]:
    """The jump between the last and first sample, and the normal sample-to-sample movement
    (95th percentile) in the first and last few milliseconds, to compare it with."""
    if len(samples) < 4:
        return 0.0, 0.0
    n = max(2, min(len(samples) // 2, int(audio.RATE * SEAM_WINDOW_MS / 1000)))
    steps = [abs(samples[i + 1] - samples[i]) for i in range(n - 1)]
    steps += [abs(samples[i + 1] - samples[i]) for i in range(len(samples) - n, len(samples) - 1)]
    steps.sort()
    return abs(samples[-1] - samples[0]), steps[int(0.95 * (len(steps) - 1))]


def silent_ends(samples: list[float]) -> tuple[float, float]:
    peak = max((abs(s) for s in samples), default=0.0)
    if peak == 0.0:
        return 0.0, 0.0
    limit = peak * audio.db_to_gain(SILENCE_DB)
    head = next(i for i, s in enumerate(samples) if abs(s) > limit)
    tail = next(i for i, s in enumerate(reversed(samples)) if abs(s) > limit)
    return head / audio.RATE, tail / audio.RATE


def seam_problems(name: str, info: MusicInfo) -> list[str]:
    problems: list[str] = []
    if not info.exact:
        return problems
    if info.seam_jump > max(0.05, 4 * info.edge_motion):
        problems.append(f"{name}: the waveform jumps by {info.seam_jump:.2f} at the loop point: "
                        "it will click each time it loops (cut at a quieter moment, or on the beat)")
    gap = info.silent_head + info.silent_tail
    if gap > MAX_LOOP_GAP:
        problems.append(f"{name}: {gap:.1f} s of silence where it loops ({info.silent_tail:.1f} s at the end, "
                        f"{info.silent_head:.1f} s at the start); a fade-out? Cut it with --end, or set loop: false")
    return problems


def temp_dir() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(prefix="gamekit-music-")
