"""sfxr: the classic retro sound effect generator (DrPetter, 2007), ported to Python.

A sound is ~23 numbers (most 0..1, ramps -1..1) kept in a small YAML file, e.g.
sounds/<id>.yaml. The presets below are sfxr's own "generate" buttons; each one is
random within limits, so a seed picks one result. The same parameters and seed always
render the same sound.
"""
from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import yaml

WAVES = ["square", "saw", "sine", "noise"]
MASTER_VOLUME = 0.05


@dataclass
class Params:
    wave: str = "square"
    base_freq: float = 0.3      # start pitch
    freq_limit: float = 0.0     # pitch at which a falling sound stops
    freq_ramp: float = 0.0      # -1..1: pitch slide down / up
    freq_dramp: float = 0.0     # -1..1: change of the slide
    duty: float = 0.0           # square wave width
    duty_ramp: float = 0.0      # -1..1
    vib_strength: float = 0.0   # vibrato depth
    vib_speed: float = 0.0
    env_attack: float = 0.0     # fade-in time
    env_sustain: float = 0.3    # hold time
    env_punch: float = 0.0      # extra loudness at the start of the hold
    env_decay: float = 0.4      # fade-out time
    lpf_freq: float = 1.0       # low-pass cutoff (1 = off): lower = duller
    lpf_ramp: float = 0.0       # -1..1
    lpf_resonance: float = 0.0
    hpf_freq: float = 0.0       # high-pass cutoff (0 = off): higher = thinner
    hpf_ramp: float = 0.0       # -1..1
    pha_offset: float = 0.0     # -1..1: phaser (flanger) delay
    pha_ramp: float = 0.0       # -1..1
    repeat_speed: float = 0.0   # restart the sound this often (0 = never)
    arp_speed: float = 0.0      # when the pitch jumps once
    arp_mod: float = 0.0        # -1..1: how far it jumps (up > 0, down < 0)
    volume: float = 0.5
    seed: int = 0               # noise randomness

    def clamped(self) -> "Params":
        out = Params(**asdict(self))
        for f in fields(self):
            if f.name in ("wave", "seed"):
                continue
            low = -1.0 if f.name.endswith(("_ramp", "_dramp")) or f.name in ("pha_offset", "arp_mod") else 0.0
            setattr(out, f.name, max(low, min(1.0, float(getattr(self, f.name)))))
        if out.wave not in WAVES:
            raise ValueError(f"wave must be one of {', '.join(WAVES)}")
        return out


# --- presets (sfxr's generator buttons) ------------------------------------------------------

def _rnd(r: random.Random, n: int) -> int:
    return r.randint(0, n)


def _frnd(r: random.Random, x: float) -> float:
    return r.random() * x


def preset(name: str, seed: int) -> Params:
    r = random.Random(seed)
    p = Params(seed=seed)
    if name in ("pickup", "coin"):
        p.base_freq = 0.4 + _frnd(r, 0.5)
        p.env_sustain = _frnd(r, 0.1)
        p.env_decay = 0.1 + _frnd(r, 0.4)
        p.env_punch = 0.3 + _frnd(r, 0.3)
        if _rnd(r, 1):
            p.arp_speed = 0.5 + _frnd(r, 0.2)
            p.arp_mod = 0.2 + _frnd(r, 0.4)
    elif name in ("laser", "shoot"):
        p.wave = WAVES[_rnd(r, 2)]
        if p.wave == "sine" and _rnd(r, 1):
            p.wave = WAVES[_rnd(r, 1)]
        p.base_freq = 0.5 + _frnd(r, 0.5)
        p.freq_limit = max(0.2, p.base_freq - 0.2 - _frnd(r, 0.6))
        p.freq_ramp = -0.15 - _frnd(r, 0.2)
        if _rnd(r, 2) == 0:
            p.base_freq = 0.3 + _frnd(r, 0.6)
            p.freq_limit = _frnd(r, 0.1)
            p.freq_ramp = -0.35 - _frnd(r, 0.3)
        if _rnd(r, 1):
            p.duty = _frnd(r, 0.5)
            p.duty_ramp = _frnd(r, 0.2)
        else:
            p.duty = 0.4 + _frnd(r, 0.5)
            p.duty_ramp = -_frnd(r, 0.7)
        p.env_sustain = 0.1 + _frnd(r, 0.2)
        p.env_decay = _frnd(r, 0.4)
        if _rnd(r, 1):
            p.env_punch = _frnd(r, 0.3)
        if _rnd(r, 2) == 0:
            p.pha_offset = _frnd(r, 0.2)
            p.pha_ramp = -_frnd(r, 0.2)
        if _rnd(r, 1):
            p.hpf_freq = _frnd(r, 0.3)
    elif name == "explosion":
        p.wave = "noise"
        if _rnd(r, 1):
            p.base_freq = 0.1 + _frnd(r, 0.4)
            p.freq_ramp = -0.1 + _frnd(r, 0.4)
        else:
            p.base_freq = 0.2 + _frnd(r, 0.7)
            p.freq_ramp = -0.2 - _frnd(r, 0.2)
        p.base_freq *= p.base_freq
        if _rnd(r, 4) == 0:
            p.freq_ramp = 0.0
        if _rnd(r, 2) == 0:
            p.repeat_speed = 0.3 + _frnd(r, 0.5)
        p.env_sustain = 0.1 + _frnd(r, 0.3)
        p.env_decay = _frnd(r, 0.5)
        if _rnd(r, 1) == 0:
            p.pha_offset = -0.3 + _frnd(r, 0.9)
            p.pha_ramp = -_frnd(r, 0.3)
        p.env_punch = 0.2 + _frnd(r, 0.6)
        if _rnd(r, 1):
            p.vib_strength = _frnd(r, 0.7)
            p.vib_speed = _frnd(r, 0.6)
        if _rnd(r, 2) == 0:
            p.arp_speed = 0.6 + _frnd(r, 0.3)
            p.arp_mod = 0.8 - _frnd(r, 1.6)
    elif name == "powerup":
        if _rnd(r, 1):
            p.wave = "saw"
        else:
            p.duty = _frnd(r, 0.6)
        if _rnd(r, 1):
            p.base_freq = 0.2 + _frnd(r, 0.3)
            p.freq_ramp = 0.1 + _frnd(r, 0.4)
            p.repeat_speed = 0.4 + _frnd(r, 0.4)
        else:
            p.base_freq = 0.2 + _frnd(r, 0.3)
            p.freq_ramp = 0.05 + _frnd(r, 0.2)
            if _rnd(r, 1):
                p.vib_strength = _frnd(r, 0.7)
                p.vib_speed = _frnd(r, 0.6)
        p.env_sustain = _frnd(r, 0.4)
        p.env_decay = 0.1 + _frnd(r, 0.4)
    elif name in ("hit", "hurt"):
        p.wave = WAVES[_rnd(r, 2)]
        if p.wave == "sine":
            p.wave = "noise"
        if p.wave == "square":
            p.duty = _frnd(r, 0.6)
        p.base_freq = 0.2 + _frnd(r, 0.6)
        p.freq_ramp = -0.3 - _frnd(r, 0.4)
        p.env_sustain = _frnd(r, 0.1)
        p.env_decay = 0.1 + _frnd(r, 0.2)
        if _rnd(r, 1):
            p.hpf_freq = _frnd(r, 0.3)
    elif name == "jump":
        p.duty = _frnd(r, 0.6)
        p.base_freq = 0.3 + _frnd(r, 0.3)
        p.freq_ramp = 0.1 + _frnd(r, 0.2)
        p.env_sustain = 0.1 + _frnd(r, 0.3)
        p.env_decay = 0.1 + _frnd(r, 0.2)
        if _rnd(r, 1):
            p.hpf_freq = _frnd(r, 0.3)
        if _rnd(r, 1):
            p.lpf_freq = 1.0 - _frnd(r, 0.6)
    elif name in ("blip", "select"):
        p.wave = WAVES[_rnd(r, 1)]
        if p.wave == "square":
            p.duty = _frnd(r, 0.6)
        p.base_freq = 0.2 + _frnd(r, 0.4)
        p.env_sustain = 0.1 + _frnd(r, 0.1)
        p.env_decay = _frnd(r, 0.2)
        p.hpf_freq = 0.1
    elif name == "random":
        p = randomize(r, seed)
    else:
        raise ValueError(f"unknown preset {name!r}; choose from {', '.join(PRESETS)}")
    return p


PRESETS = ["pickup", "laser", "explosion", "powerup", "hit", "jump", "blip", "random"]


def randomize(r: random.Random, seed: int) -> Params:
    """sfxr's "randomize" button: anything goes, mostly noise and squeaks."""
    p = Params(seed=seed)
    p.base_freq = (_frnd(r, 2.0) - 1.0) ** 2
    if _rnd(r, 1):
        p.base_freq = (_frnd(r, 2.0) - 1.0) ** 3 + 0.5
    p.base_freq = max(0.0, min(1.0, p.base_freq))
    p.freq_ramp = (_frnd(r, 2.0) - 1.0) ** 5
    if p.base_freq > 0.7 and p.freq_ramp > 0.2:
        p.freq_ramp = -p.freq_ramp
    if p.base_freq < 0.2 and p.freq_ramp < -0.05:
        p.freq_ramp = -p.freq_ramp
    p.freq_dramp = (_frnd(r, 2.0) - 1.0) ** 3
    p.duty = _frnd(r, 2.0) - 1.0
    p.duty_ramp = (_frnd(r, 2.0) - 1.0) ** 3
    p.vib_strength = (_frnd(r, 2.0) - 1.0) ** 3
    p.vib_speed = _frnd(r, 2.0) - 1.0
    p.env_attack = (_frnd(r, 2.0) - 1.0) ** 3
    p.env_sustain = (_frnd(r, 2.0) - 1.0) ** 2
    p.env_decay = _frnd(r, 2.0) - 1.0
    p.env_punch = (_frnd(r, 0.8)) ** 2
    if p.env_attack + p.env_sustain + p.env_decay < 0.2:
        p.env_sustain += 0.2 + _frnd(r, 0.3)
        p.env_decay += 0.2 + _frnd(r, 0.3)
    p.lpf_resonance = _frnd(r, 2.0) - 1.0
    p.lpf_freq = 1.0 - _frnd(r, 1.0) ** 3
    p.lpf_ramp = (_frnd(r, 2.0) - 1.0) ** 3
    if p.lpf_freq < 0.1 and p.lpf_ramp < -0.05:
        p.lpf_ramp = -p.lpf_ramp
    p.hpf_freq = _frnd(r, 1.0) ** 5
    p.hpf_ramp = (_frnd(r, 2.0) - 1.0) ** 5
    p.pha_offset = (_frnd(r, 2.0) - 1.0) ** 3
    p.pha_ramp = (_frnd(r, 2.0) - 1.0) ** 3
    p.repeat_speed = _frnd(r, 2.0) - 1.0
    p.arp_speed = _frnd(r, 2.0) - 1.0
    p.arp_mod = _frnd(r, 2.0) - 1.0
    p.wave = WAVES[_rnd(r, 3)]
    return p.clamped()


def mutate(p: Params, seed: int, amount: float = 0.05) -> Params:
    """sfxr's "mutate" button: nudge about half the numbers a little."""
    r = random.Random(seed)
    out = Params(**asdict(p))
    for f in fields(p):
        if f.name in ("wave", "seed", "volume"):
            continue
        if _rnd(r, 1):
            setattr(out, f.name, getattr(out, f.name) + _frnd(r, amount * 2) - amount)
    out.seed = seed
    return out.clamped()


TWEAKS = {
    # word -> what it changes (the same table as the sfx-make skill's "User says / Change")
    "higher": "base_freq up",
    "lower": "base_freq down",
    "shorter": "env_sustain and env_decay down",
    "longer": "env_sustain and env_decay up",
    "punchier": "env_punch up, env_attack 0",
    "softer": "lpf_freq down, saw becomes square",
    "thinner": "hpf_freq up",
    "fuller": "hpf_freq down",
    "falling": "freq_ramp down",
    "rising": "freq_ramp up",
    "wobble": "vib_strength and vib_speed up",
    "steady": "no vibrato",
}


def tweak(p: Params, word: str) -> Params:
    """One small step in the direction of a TWEAKS word, e.g. tweak(p, "higher")."""
    out = Params(**asdict(p))
    if word == "higher":
        out.base_freq += 0.05
    elif word == "lower":
        out.base_freq -= 0.05
    elif word in ("shorter", "longer"):
        scale = 0.7 if word == "shorter" else 1.4
        out.env_sustain = out.env_sustain * scale if out.env_sustain else (0.0 if word == "shorter" else 0.05)
        out.env_decay = out.env_decay * scale if out.env_decay else (0.0 if word == "shorter" else 0.05)
    elif word == "punchier":
        out.env_punch += 0.2
        out.env_attack = 0.0
    elif word == "softer":
        out.lpf_freq *= 0.75
        if out.wave == "saw":
            out.wave = "square"
    elif word == "thinner":
        out.hpf_freq += 0.1
    elif word == "fuller":
        out.hpf_freq = max(0.0, out.hpf_freq - 0.1)
    elif word == "falling":
        out.freq_ramp -= 0.15
    elif word == "rising":
        out.freq_ramp += 0.15
    elif word == "wobble":
        out.vib_strength += 0.2
        out.vib_speed += 0.2
    elif word == "steady":
        out.vib_strength = 0.0
    else:
        raise ValueError(f"unknown tweak {word!r}; choose from {', '.join(TWEAKS)}")
    return out.clamped()


# --- files ---------------------------------------------------------------------------------

HEADER = """# sfxr sound parameters (gamekit). Most are 0..1; *_ramp, pha_offset and arp_mod are -1..1.
# Edit, then run `gamekit sfx make <id>`. wave: square | saw | sine | noise.
"""


def load(path: Path) -> Params:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected sfxr parameters")
    known = {f.name for f in fields(Params)}
    unknown = sorted(set(data) - known - {"preset"})
    if unknown:
        raise ValueError(f"{path}: unknown parameters {', '.join(unknown)}")
    return Params(**{k: v for k, v in data.items() if k in known}).clamped()


def save(path: Path, p: Params, preset_name: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(p.clamped())
    for key, value in data.items():
        if isinstance(value, float):
            data[key] = round(value, 4)
    body = ({"preset": preset_name} if preset_name else {}) | data
    path.write_text(HEADER + yaml.safe_dump(body, sort_keys=False), encoding="utf-8")


# --- synthesis -----------------------------------------------------------------------------

def render(params: Params, max_seconds: float = 10.0) -> list[float]:
    """Renders at 44100 Hz mono, 8x supersampled, exactly like sfxr's SynthSample."""
    p = params.clamped()
    wave_type = WAVES.index(p.wave)
    noise_rng = random.Random(p.seed)
    s: dict = {}

    def reset(restart: bool) -> None:
        s["fperiod"] = 100.0 / (p.base_freq ** 2 + 0.001)
        s["fmaxperiod"] = 100.0 / (p.freq_limit ** 2 + 0.001)
        s["fslide"] = 1.0 - p.freq_ramp ** 3 * 0.01
        s["fdslide"] = -(p.freq_dramp ** 3) * 0.000001
        s["square_duty"] = 0.5 - p.duty * 0.5
        s["square_slide"] = -p.duty_ramp * 0.00005
        s["arp_mod"] = 1.0 - p.arp_mod ** 2 * 0.9 if p.arp_mod >= 0 else 1.0 + p.arp_mod ** 2 * 10.0
        s["arp_time"] = 0
        s["arp_limit"] = 0 if p.arp_speed == 1.0 else int((1.0 - p.arp_speed) ** 2 * 20000 + 32)
        if restart:
            return
        s["fltp"] = 0.0
        s["fltdp"] = 0.0
        s["fltw"] = p.lpf_freq ** 3 * 0.1
        s["fltw_d"] = 1.0 + p.lpf_ramp * 0.0001
        s["fltdmp"] = min(0.8, 5.0 / (1.0 + p.lpf_resonance ** 2 * 20.0) * (0.01 + s["fltw"]))
        s["fltphp"] = 0.0
        s["flthp"] = p.hpf_freq ** 2 * 0.1
        s["flthp_d"] = 1.0 + p.hpf_ramp * 0.0003
        s["vib_phase"] = 0.0
        s["vib_speed"] = p.vib_speed ** 2 * 0.01
        s["vib_amp"] = p.vib_strength * 0.5
        s["env_vol"] = 0.0
        s["env_stage"] = 0
        s["env_time"] = 0
        s["env_length"] = [int(p.env_attack ** 2 * 100000), int(p.env_sustain ** 2 * 100000),
                           int(p.env_decay ** 2 * 100000)]
        fphase = p.pha_offset ** 2 * 1020.0
        s["fphase"] = -fphase if p.pha_offset < 0 else fphase
        fdphase = p.pha_ramp ** 2 * 1.0
        s["fdphase"] = -fdphase if p.pha_ramp < 0 else fdphase
        s["iphase"] = abs(int(s["fphase"]))
        s["ipp"] = 0
        s["phaser"] = [0.0] * 1024
        s["noise"] = [noise_rng.random() * 2.0 - 1.0 for _ in range(32)]
        s["phase"] = 0
        s["rep_time"] = 0
        s["rep_limit"] = 0 if p.repeat_speed == 0.0 else int((1.0 - p.repeat_speed) ** 2 * 20000 + 32)

    reset(False)
    out: list[float] = []
    limit = int(max_seconds * 44100)
    gain = MASTER_VOLUME * 2.0 * p.volume
    while len(out) < limit:
        s["rep_time"] += 1
        if s["rep_limit"] != 0 and s["rep_time"] >= s["rep_limit"]:
            s["rep_time"] = 0
            reset(True)
        s["arp_time"] += 1
        if s["arp_limit"] != 0 and s["arp_time"] >= s["arp_limit"]:
            s["arp_limit"] = 0
            s["fperiod"] *= s["arp_mod"]
        s["fslide"] += s["fdslide"]
        s["fperiod"] *= s["fslide"]
        if s["fperiod"] > s["fmaxperiod"]:
            s["fperiod"] = s["fmaxperiod"]
            if p.freq_limit > 0.0:
                break
        rfperiod = s["fperiod"]
        if s["vib_amp"] > 0.0:
            s["vib_phase"] += s["vib_speed"]
            rfperiod = s["fperiod"] * (1.0 + math.sin(s["vib_phase"]) * s["vib_amp"])
        period = max(8, int(rfperiod))
        s["square_duty"] = max(0.0, min(0.5, s["square_duty"] + s["square_slide"]))

        s["env_time"] += 1
        if s["env_time"] > s["env_length"][s["env_stage"]]:
            s["env_time"] = 0
            s["env_stage"] += 1
            if s["env_stage"] == 3:
                break
        length = max(1, s["env_length"][s["env_stage"]])
        if s["env_stage"] == 0:
            s["env_vol"] = s["env_time"] / length
        elif s["env_stage"] == 1:
            s["env_vol"] = 1.0 + (1.0 - s["env_time"] / length) * 2.0 * p.env_punch
        else:
            s["env_vol"] = 1.0 - s["env_time"] / length

        s["fphase"] += s["fdphase"]
        s["iphase"] = min(1023, abs(int(s["fphase"])))
        if s["flthp_d"] != 0.0:
            s["flthp"] = max(0.00001, min(0.1, s["flthp"] * s["flthp_d"]))

        ssample = 0.0
        for _ in range(8):
            s["phase"] += 1
            if s["phase"] >= period:
                s["phase"] %= period
                if wave_type == 3:
                    s["noise"] = [noise_rng.random() * 2.0 - 1.0 for _ in range(32)]
            fp = s["phase"] / period
            if wave_type == 0:
                sample = 0.5 if fp < s["square_duty"] else -0.5
            elif wave_type == 1:
                sample = 1.0 - fp * 2.0
            elif wave_type == 2:
                sample = math.sin(fp * 2.0 * math.pi)
            else:
                sample = s["noise"][s["phase"] * 32 // period]
            pp = s["fltp"]
            s["fltw"] = max(0.0, min(0.1, s["fltw"] * s["fltw_d"]))
            if p.lpf_freq != 1.0:
                s["fltdp"] += (sample - s["fltp"]) * s["fltw"]
                s["fltdp"] -= s["fltdp"] * s["fltdmp"]
            else:
                s["fltp"] = sample
                s["fltdp"] = 0.0
            s["fltp"] += s["fltdp"]
            s["fltphp"] += s["fltp"] - pp
            s["fltphp"] -= s["fltphp"] * s["flthp"]
            sample = s["fltphp"]
            phaser = s["phaser"]
            phaser[s["ipp"] & 1023] = sample
            sample += phaser[(s["ipp"] - s["iphase"] + 1024) & 1023]
            s["ipp"] = (s["ipp"] + 1) & 1023
            ssample += sample * s["env_vol"]
        out.append(max(-1.0, min(1.0, ssample / 8.0 * gain)))
    return out
