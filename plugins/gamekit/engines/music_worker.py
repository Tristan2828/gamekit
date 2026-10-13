"""Music worker (gamekit engine "music"). gamekit starts it in the engine's own Python and talks to it over
stdin/stdout: one JSON request a line in, one "@@"-prefixed JSON reply a line out, plus @@{"step": "..."}
lines while it works.

The model is ACE-Step 1.5 (MIT licence): music from a description, with a "planner" language model that
fills in structure first. Its code is a git checkout set up by `gamekit engines setup music`
(GAMEKIT_ENGINE_CODE); model files live in engines/models/acestep and download on first use.
Adapted from Hearthtone's music worker and make.py, with thanks.

On a 16 GB card the models stay on the card (no CPU offload: with 16 GB of system memory, offloading made
Windows page to disk for the picture model). GAMEKIT_MUSIC_OFFLOAD=1 parks them in system memory instead,
for smaller cards. Measured on an RX 7800 XT: loading ~40 s, 30 s of music ~50 s, 60 s ~90 s; with the
planner ~7 minutes a take.

Request: {"prompt", "out", "seconds", "bpm", "key", "lyrics", "instrumental", "steps", "seed", "planner"}
Reply:   {"ok": true, "seed", "seconds", "planner"}
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

CODE = Path(os.environ.get("GAMEKIT_ENGINE_CODE", ""))
MODELS = Path(os.environ.get("GAMEKIT_MODELS", Path(__file__).resolve().parent / "models"))
CHECKPOINTS = MODELS / "acestep"
DIT = os.environ.get("GAMEKIT_MUSIC_MODEL", "acestep-v15-turbo")
PLANNER = os.environ.get("GAMEKIT_MUSIC_PLANNER", "acestep-5Hz-lm-1.7B")  # used only when asked for
OFFLOAD = os.environ.get("GAMEKIT_MUSIC_OFFLOAD") == "1"

os.environ["ACESTEP_CHECKPOINTS_DIR"] = str(CHECKPOINTS)
sys.path.insert(0, str(CODE))


def reply(obj):
    sys.stdout.write("@@" + json.dumps(obj) + "\n")
    sys.stdout.flush()


def step(text):
    reply({"step": text})


def single_machine_distributed():
    """AMD's PyTorch for Windows leaves out torch.distributed (training across machines), but a library ACE-Step
    uses (vector_quantize_pytorch) imports parts of it. On one PC "distributed" always means "one machine", so
    harmless stand-ins are enough: not initialized, world size 1, collective operations do nothing.
    (ACE-Step discussion #404 patches the library's file instead; this survives reinstalls.)"""
    import types

    import torch.distributed as dist

    if dist.is_available():
        return
    one_machine = {
        "is_initialized": lambda: False, "get_world_size": lambda group=None: 1, "get_rank": lambda group=None: 0,
        "all_reduce": lambda tensor, *a, **k: None, "broadcast": lambda tensor, *a, **k: None,
        "barrier": lambda *a, **k: None,
        "all_gather": lambda out, tensor, *a, **k: [o.copy_(tensor) for o in out] and None,
    }
    for name, stand_in in one_machine.items():
        if not hasattr(dist, name):
            setattr(dist, name, stand_in)
    if not hasattr(dist, "group"):
        dist.group = types.SimpleNamespace(WORLD=None)
    nn = types.ModuleType("torch.distributed.nn")
    nn.all_reduce = lambda tensor, *a, **k: tensor
    sys.modules["torch.distributed.nn"] = nn
    dist.nn = nn


class Composer:
    """The music model, loaded at start; the planner only when a request asks for it (on an RX 7800 XT with
    ACE-Step's plain-PyTorch planner it took ~4 extra minutes a take and once produced invalid output)."""

    def __init__(self):
        single_machine_distributed()
        from loguru import logger

        logger.remove()
        logger.add(sys.stderr, level="WARNING")
        from acestep.handler import AceStepHandler
        from acestep.llm_inference import LLMHandler

        if not (CODE / "acestep").is_dir():
            raise RuntimeError(f"ACE-Step's code is missing from {CODE}: run `gamekit engines setup music`")
        CHECKPOINTS.mkdir(parents=True, exist_ok=True)
        if not (CHECKPOINTS / DIT).is_dir():
            step("Downloading the music model (about 10 GB, first time only)")
        step("Loading the music model")
        self.dit = AceStepHandler()
        status, ok = self.dit.initialize_service(project_root=str(CODE), config_path=DIT, device="cuda",
                                                 offload_to_cpu=OFFLOAD, offload_dit_to_cpu=False, quantization=None)
        if not ok:
            raise RuntimeError(f"the music model didn't load: {status}")
        self.llm = LLMHandler()
        self.planner_ready = False

    def planner(self):
        if not self.planner_ready:
            if not (CHECKPOINTS / PLANNER).is_dir():
                step("Downloading the planner (first time only)")
            step("Loading the planner")
            status, ok = self.llm.initialize(checkpoint_dir=str(CHECKPOINTS), lm_model_path=PLANNER, backend="pt",
                                             device="cuda", offload_to_cpu=OFFLOAD)
            if not ok:
                raise RuntimeError(f"the planner didn't load: {status}")
            self.planner_ready = True

    def compose(self, r):
        from acestep.inference import GenerationConfig, GenerationParams, generate_music

        thinking = bool(r.get("planner"))
        if thinking:
            self.planner()
        instrumental = bool(r.get("instrumental", True)) or not str(r.get("lyrics", "")).strip()
        seed = r.get("seed")
        params = GenerationParams(
            caption=r["prompt"], lyrics="[Instrumental]" if instrumental else r["lyrics"],
            instrumental=instrumental, vocal_language="unknown" if instrumental else "en",
            bpm=r.get("bpm"), keyscale=r.get("key") or "", duration=float(r.get("seconds", 60)),
            inference_steps=int(r.get("steps", 8)), thinking=thinking, use_cot_caption=False, use_cot_language=False)
        config = GenerationConfig(batch_size=1, audio_format="wav", use_random_seed=seed is None,
                                  seeds=None if seed is None else [int(seed)])
        step("Planning and composing (slow)" if thinking else "Composing")
        with tempfile.TemporaryDirectory() as raw:
            result = generate_music(self.dit, self.llm, params, config, save_dir=raw)
            if not result.success:
                raise RuntimeError(str(result.error))
            audio = result.audios[0]
            Path(r["out"]).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(audio["path"], r["out"])
        used = audio.get("params", {}).get("seed", seed)
        return {"ok": True, "seed": used, "seconds": float(r.get("seconds", 60)), "planner": thinking}


def main():
    try:
        composer = Composer()
    except BaseException as e:  # ACE-Step exits (SystemExit) when a model won't load
        reply({"ready": False, "error": f"{type(e).__name__}: {e}"[:800]})
        return
    reply({"ready": True})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            reply(composer.compose(json.loads(line)))
        except Exception as e:
            reply({"ok": False, "error": f"{type(e).__name__}: {e}"[:800]})


if __name__ == "__main__":
    main()
