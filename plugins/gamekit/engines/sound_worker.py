"""Sound-effect worker (gamekit engine "sound"). gamekit starts it in the engine's own Python and talks to it
over stdin/stdout: one JSON request a line in, one "@@"-prefixed JSON reply a line out, plus
@@{"step": "..."} lines while it works.

The model is Stable Audio 3 Small SFX (Stability AI Community License: free, also commercially under $1M a
year in revenue). It is gated: the person accepts its license once on Hugging Face, and the first load
downloads it (needs `hf auth login` on this PC, or a copy already in engines/hf). Its code is a git checkout
installed by `gamekit engines setup sound`. Adapted from Hearthtone's sfx worker, with thanks.

Request: {"prompt", "out", "seconds", "steps", "seed", "mono", "loop"}
Reply:   {"ok": true, "seed", "seconds"}
"""
import json
import os
import random
import sys
from pathlib import Path

# Already in the Hugging Face cache (downloaded once, or copied in): load it offline. Online, the library checks
# the gated repo first and is refused without a sign-in on this PC, even though the files are right here.
CACHED = Path(os.environ.get("HF_HOME", "")) / "hub" / "models--stabilityai--stable-audio-3-small-sfx" / "snapshots"
if os.environ.get("HF_HOME") and CACHED.is_dir() and any(CACHED.iterdir()):
    os.environ["HF_HUB_OFFLINE"] = "1"

LOCKED = ("The sound model is locked until you accept its license: open "
          "https://huggingface.co/stabilityai/stable-audio-3-small-sfx, sign in, press Agree, then run "
          "`hf auth login` on this PC with a Read token (see the Sounds tab).")


def reply(obj):
    sys.stdout.write("@@" + json.dumps(obj) + "\n")
    sys.stdout.flush()


def step(text):
    reply({"step": text})


def finish(audio, rate, r):
    """Tidy one generated sound: optional mono and loop, trim the silent tail, level it, fade the ends."""
    import numpy as np

    a = audio.astype(np.float32)
    if r.get("mono"):
        a = a.mean(axis=0, keepdims=True)
    n = a.shape[1]
    if r.get("loop"):
        # The sound was made a second longer than asked; blend that extra second over the start.
        x = min(rate, n // 4)
        ramp = np.linspace(0.0, 1.0, x, dtype=np.float32)
        a[:, :x] = a[:, :x] * ramp + a[:, n - x:] * (1 - ramp)
        a = a[:, :n - x]
    else:
        level = np.abs(a).max(axis=0)
        loud = np.nonzero(level > 0.004 * max(level.max(), 1e-9))[0]
        if len(loud):
            a = a[:, :min(n, loud[-1] + int(0.15 * rate))]
        f = min(a.shape[1], int(0.02 * rate))
        a[:, -f:] *= np.linspace(1.0, 0.0, f, dtype=np.float32)
        g = min(64, a.shape[1])
        a[:, :g] *= np.linspace(0.0, 1.0, g, dtype=np.float32)
    peak = np.abs(a).max()
    if peak > 0:
        a *= 0.89 / peak
    return a


def main():
    try:
        import soundfile as sf
        import torch
        from stable_audio_3 import StableAudioModel

        step("Loading the sound model")
        model = StableAudioModel.from_pretrained("small-sfx")
        rate = int(model.model.sample_rate)
    except Exception as e:
        text = f"{type(e).__name__}: {e}"
        locked = any(w in text for w in ("401", "403", "gated", "Gated", "restricted", "authenticated"))
        reply({"ready": False, "error": LOCKED if locked else text[:800]})
        return
    reply({"ready": True})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        try:
            seed = r["seed"] if r.get("seed") is not None else random.randrange(1, 2**31 - 1)
            seconds = float(r["seconds"]) + (1.0 if r.get("loop") else 0.0)
            step("Making the sound")
            with torch.inference_mode():
                out = model.generate(prompt=r["prompt"], duration=seconds, steps=int(r.get("steps", 8)), seed=seed)
            audio = finish(out[0].detach().float().cpu().numpy(), rate, r)
            Path(r["out"]).parent.mkdir(parents=True, exist_ok=True)
            sf.write(r["out"], audio.T, rate, subtype="PCM_16")
            reply({"ok": True, "seed": seed, "seconds": round(audio.shape[1] / rate, 2)})
        except Exception as e:
            reply({"ok": False, "error": f"{type(e).__name__}: {e}"[:800]})


if __name__ == "__main__":
    main()
