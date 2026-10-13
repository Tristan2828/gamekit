"""Voice worker (gamekit engine "voice"). gamekit starts it in the engine's own Python and talks to it over
stdin/stdout: one JSON request a line in, one "@@"-prefixed JSON reply a line out, plus @@{"step": "..."}
lines while it works.

The model is Qwen3-TTS 1.7B VoiceDesign (Apache 2.0): it reads the words in a voice described in plain
language ("an old storyteller, deep warm voice..." plus how: "whispering by a fire"). Adapted from
Hearthtone's voice worker, with thanks.

Request: {"text", "who", "tone", "language", "seed", "out"}
Reply:   {"ok": true, "seed", "seconds"}
"""
import json
import os
import random
import sys
from pathlib import Path

MODELS = Path(os.environ.get("GAMEKIT_MODELS", Path(__file__).resolve().parent / "models"))
REPO = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
WEIGHTS = MODELS / "Qwen3-TTS-12Hz-1.7B-VoiceDesign"


def reply(obj):
    sys.stdout.write("@@" + json.dumps(obj) + "\n")
    sys.stdout.flush()


def step(text):
    reply({"step": text})


def tidy(audio, rate):
    """Trim the silence at both ends, leave a short breath of it, and level the reading."""
    import numpy as np

    a = np.asarray(audio, dtype=np.float32).reshape(-1)
    level = np.abs(a)
    loud = np.nonzero(level > 0.01 * max(float(level.max()), 1e-9))[0]
    if len(loud):
        a = a[max(0, loud[0] - int(0.05 * rate)):min(len(a), loud[-1] + int(0.25 * rate))]
    peak = float(np.abs(a).max()) if len(a) else 0.0
    if peak > 0:
        a = a * (0.89 / peak)
    return a


def main():
    try:
        import soundfile as sf
        import torch
        from qwen_tts import Qwen3TTSModel

        if not (WEIGHTS / "model.safetensors").is_file():
            step("Downloading the voice model (about 4 GB, first time only)")
            from huggingface_hub import snapshot_download
            snapshot_download(REPO, local_dir=str(WEIGHTS))
        step("Loading the voice model")
        model = Qwen3TTSModel.from_pretrained(str(WEIGHTS), device_map="cuda:0", dtype=torch.bfloat16)
    except Exception as e:
        reply({"ready": False, "error": f"{type(e).__name__}: {e}"[:800]})
        return
    reply({"ready": True})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        try:
            seed = r["seed"] if r.get("seed") is not None else random.randrange(1, 2**31 - 1)
            torch.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            # The voice and the way it speaks are one description to the model.
            instruct = " ".join(part.strip() for part in (r.get("who", ""), r.get("tone", "")) if part.strip())
            step("Reading")
            with torch.inference_mode():
                wavs, rate = model.generate_voice_design(
                    text=r["text"], language=r.get("language") or "English",
                    instruct=instruct or "A clear, natural speaking voice.")
            audio = tidy(wavs[0], rate)
            Path(r["out"]).parent.mkdir(parents=True, exist_ok=True)
            sf.write(r["out"], audio, rate, subtype="PCM_16")
            reply({"ok": True, "seed": seed, "seconds": round(len(audio) / rate, 2)})
        except Exception as e:
            reply({"ok": False, "error": f"{type(e).__name__}: {e}"[:800]})


if __name__ == "__main__":
    main()
