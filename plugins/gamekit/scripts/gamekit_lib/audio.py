"""Sound files: read anything, clean it up, write game-ready WAV, and describe it in numbers.

Game-ready sound effects here mean: mono, 16-bit, 44100 Hz WAV, silence trimmed from both
ends, peak normalized (default -1 dBFS) with a tiny fade-out so a trimmed tail doesn't click.

PCM WAV files are read with the standard library; everything else (mp3, ogg, flac, float WAV)
is decoded with ffmpeg, found via $GAMEKIT_FFMPEG, PATH, or the usual install folders.
Samples are plain lists of floats in -1..1; no numpy needed.
"""
from __future__ import annotations

import array
import math
import os
import shutil
import struct
import subprocess
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

RATE = 44100
FFMPEG_PATHS = [
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
]


class AudioError(Exception):
    pass


def find_ffmpeg() -> str:
    configured = os.environ.get("GAMEKIT_FFMPEG")
    if configured:
        if Path(configured).exists():
            return configured
        raise AudioError(f"GAMEKIT_FFMPEG points to {configured}, which doesn't exist")
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in FFMPEG_PATHS:
        if Path(candidate).exists():
            return candidate
    raise AudioError("ffmpeg not found (needed for mp3 / ogg / flac and for music). Install it "
                     "(Windows: `winget install ffmpeg`), or set GAMEKIT_FFMPEG to ffmpeg.exe's full path.")


# --- reading -----------------------------------------------------------------------------

def read(path: Path) -> list[float]:
    """Any sound file -> mono samples at 44100 Hz."""
    if not path.exists():
        raise AudioError(f"{path} not found")
    if path.suffix.lower() == ".wav":
        try:
            return _read_pcm_wav(path)
        except (wave.Error, EOFError, AudioError):
            pass  # float or compressed WAV: let ffmpeg decode it
    return _read_ffmpeg(path)


def _read_pcm_wav(path: Path) -> list[float]:
    with wave.open(str(path), "rb") as w:
        channels, width, rate, count = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(count)
    if width == 1:
        values = [(b - 128) / 128.0 for b in raw]
    elif width == 2:
        data = array.array("h", raw)
        if sys.byteorder == "big":
            data.byteswap()
        values = [v / 32768.0 for v in data]
    elif width == 3:
        values = [int.from_bytes(raw[i:i + 3], "little", signed=True) / 8388608.0 for i in range(0, len(raw), 3)]
    elif width == 4:
        data = array.array("i", raw)
        if sys.byteorder == "big":
            data.byteswap()
        values = [v / 2147483648.0 for v in data]
    else:
        raise AudioError(f"{path}: unsupported sample width {width}")
    if channels > 1:
        values = [sum(values[i:i + channels]) / channels for i in range(0, len(values), channels)]
    return resample(values, rate, RATE) if rate != RATE else values


def _read_ffmpeg(path: Path) -> list[float]:
    command = [find_ffmpeg(), "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(RATE), "-"]
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        raise AudioError(f"ffmpeg couldn't read {path}: {result.stderr.decode(errors='replace').strip()}")
    data = array.array("f")
    data.frombytes(result.stdout[: len(result.stdout) // 4 * 4])
    if sys.byteorder == "big":
        data.byteswap()
    return list(data)


def resample(samples: list[float], src: int, dst: int) -> list[float]:
    """Linear resampling; fine for short game sounds."""
    if not samples or src == dst:
        return samples
    count = max(1, int(len(samples) * dst / src))
    step = src / dst
    out = []
    last = len(samples) - 1
    for i in range(count):
        pos = i * step
        j = int(pos)
        frac = pos - j
        a = samples[min(j, last)]
        b = samples[min(j + 1, last)]
        out.append(a + (b - a) * frac)
    return out


# --- processing ----------------------------------------------------------------------------

def db_to_gain(db: float) -> float:
    return 10 ** (db / 20)


def trim(samples: list[float], threshold_db: float = -50.0, pad_ms: float = 5.0) -> list[float]:
    """Cuts near-silence from both ends (relative to the sound's own peak), keeping a few ms."""
    peak = max((abs(s) for s in samples), default=0.0)
    if peak == 0.0:
        return []
    limit = peak * db_to_gain(threshold_db)
    start = next(i for i, s in enumerate(samples) if abs(s) > limit)
    end = len(samples) - next(i for i, s in enumerate(reversed(samples)) if abs(s) > limit)
    pad = int(RATE * pad_ms / 1000)
    return samples[max(0, start - pad): min(len(samples), end + pad)]


def normalize(samples: list[float], peak_db: float = -1.0) -> list[float]:
    peak = max((abs(s) for s in samples), default=0.0)
    if peak == 0.0:
        return samples
    gain = db_to_gain(peak_db) / peak
    return [s * gain for s in samples]


def fade_out(samples: list[float], ms: float = 8.0) -> list[float]:
    n = min(len(samples), int(RATE * ms / 1000))
    if n == 0:
        return samples
    out = samples[:]
    for i in range(n):
        out[len(out) - n + i] *= 1.0 - (i + 1) / n
    return out


def clean(samples: list[float], do_trim: bool = True, peak_db: float = -1.0) -> list[float]:
    if do_trim:
        samples = trim(samples)
    if not samples or max(abs(s) for s in samples) == 0.0:
        raise AudioError("the sound is silent")
    return fade_out(normalize(samples, peak_db))


# --- writing -------------------------------------------------------------------------------

def write_wav(path: Path, samples: list[float]) -> None:
    """16-bit mono 44100 Hz PCM."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = array.array("h", (max(-32768, min(32767, round(s * 32767))) for s in samples))
    if sys.byteorder == "big":
        data.byteswap()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())


# --- describing (Claude can't listen, so it reads these numbers) -----------------------------

@dataclass
class Info:
    seconds: float
    peak_db: float
    rms_db: float
    brightness: float          # zero crossings per second: rough "how high / hissy" it sounds
    attack_ms: float           # time to reach 90% of the peak
    envelope: list[float]      # loudness over time, 0..1, in equal slices
    clipped: int               # samples at full scale


def to_db(value: float) -> float:
    return 20 * math.log10(value) if value > 0 else -120.0


def describe(samples: list[float], slices: int = 24) -> Info:
    if not samples:
        return Info(0.0, -120.0, -120.0, 0.0, 0.0, [0.0] * slices, 0)
    peak = max(abs(s) for s in samples)
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    crossings = sum(1 for a, b in zip(samples, samples[1:]) if (a < 0) != (b < 0))
    seconds = len(samples) / RATE
    target = peak * 0.9
    attack = next((i for i, s in enumerate(samples) if abs(s) >= target), 0) / RATE * 1000
    size = max(1, math.ceil(len(samples) / slices))
    levels = [max((abs(s) for s in samples[i:i + size]), default=0.0) for i in range(0, len(samples), size)]
    top = max(levels) or 1.0
    return Info(seconds, to_db(peak), to_db(rms), crossings / seconds if seconds else 0.0, attack,
                [lvl / top for lvl in levels], sum(1 for s in samples if abs(s) >= 0.999))


def envelope_bar(levels: list[float]) -> str:
    blocks = " .:-=+*#%@"
    return "".join(blocks[min(len(blocks) - 1, int(v * (len(blocks) - 1) + 0.5))] for v in levels)


def wav_format(path: Path) -> tuple[int, int, int, float]:
    """(channels, bits, rate, seconds) of a PCM WAV; raises AudioError if it isn't one."""
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnchannels(), w.getsampwidth() * 8, w.getframerate(), w.getnframes() / w.getframerate()
    except (wave.Error, EOFError, struct.error) as error:
        raise AudioError(f"{path.name} is not a PCM WAV file ({error})") from None
