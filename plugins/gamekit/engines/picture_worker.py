"""Picture worker (gamekit engine "picture"). gamekit starts it in the engine's own Python and talks to it
over stdin/stdout: one JSON request a line in, one "@@"-prefixed JSON reply a line out, plus
@@{"step": "..."} lines while it works.

The model is FLUX.2 klein 4B (Black Forest Labs, Apache 2.0): a picture from a description, optionally
working from pictures you give it ("the same character seen from behind"). Adapted from Hearthtone's
picture worker, with thanks.

How it uses the graphics card (measured on an RX 7800 XT, 16 GB, with 16 GB of system memory):
- 15 GB or more ("resident"): the picture model (8 GB) and decoder stay on the card. The text model is loaded,
  squeezed to 8-bit (4 GB), only to read a new description (~15 s) and then dropped; the reading is reused for
  more takes, about 10 s each. Keeping the text model (or both big parts) in system memory made Windows page
  to disk: minutes a picture.
- less ("offload", or GAMEKIT_PICTURE_MODE=offload): both parts squeezed to 8-bit and taking turns on the card.

Request: {"prompt", "out", "width", "height", "steps", "seed", "tile", "refs": [paths]}
Reply:   {"ok": true, "seed", "width", "height"}
"""
import json
import os
import random
import sys
from pathlib import Path

MODELS = Path(os.environ.get("GAMEKIT_MODELS", Path(__file__).resolve().parent / "models"))
REPO = "black-forest-labs/FLUX.2-klein-4B"
WEIGHTS = MODELS / "FLUX.2-klein-4B"


def reply(obj):
    sys.stdout.write("@@" + json.dumps(obj) + "\n")
    sys.stdout.flush()


def step(text):
    reply({"step": text})


def tileable(image):
    """Make a picture repeat without a seam: the middle is kept, and towards the edges it fades into a copy of
    itself shifted by half, whose edges are the original's (seamless) middle."""
    import numpy as np
    from PIL import Image

    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    h, w = a.shape[:2]
    shifted = np.roll(a, (h // 2, w // 2), axis=(0, 1))
    y = np.abs(np.linspace(-1, 1, h))[:, None]
    x = np.abs(np.linspace(-1, 1, w))[None, :]
    edge = np.maximum(x, y)                                   # 0 in the middle, 1 at the border
    keep = np.clip((0.92 - edge) / 0.34, 0, 1)[..., None]     # 1 = original, 0 = shifted copy
    keep = keep * keep * (3 - 2 * keep)
    return Image.fromarray(np.clip(a * keep + shifted * (1 - keep), 0, 255).astype(np.uint8))


class Painter:
    def __init__(self):
        import torch
        from diffusers import Flux2KleinPipeline
        from transformers import QuantoConfig, Qwen3ForCausalLM

        if not (WEIGHTS / "transformer" / "diffusion_pytorch_model.safetensors").is_file():
            step("Downloading the picture model (about 16 GB, first time only)")
            from huggingface_hub import snapshot_download
            snapshot_download(REPO, local_dir=str(WEIGHTS),
                              ignore_patterns=["flux-2-klein-4b.safetensors", "*.png", "*.jpg"])
        self.torch = torch
        card = torch.cuda.get_device_properties(0).total_memory / 2**30 if torch.cuda.is_available() else 0
        self.mode = os.environ.get("GAMEKIT_PICTURE_MODE") or ("resident" if card >= 15 else "offload")
        step("Loading the picture model")
        self.load_text = lambda: Qwen3ForCausalLM.from_pretrained(
            str(WEIGHTS), subfolder="text_encoder", dtype=torch.bfloat16, quantization_config=QuantoConfig(weights="int8"))
        if self.mode == "resident":
            # no text model kept: it's loaded (squeezed) for each new description and dropped after reading it
            self.pipe = Flux2KleinPipeline.from_pretrained(str(WEIGHTS), text_encoder=None, torch_dtype=torch.bfloat16)
            self.pipe.transformer.to("cuda")
            self.pipe.vae.to("cuda")
        else:
            from diffusers import QuantoConfig as DiffusersQuanto
            from diffusers.quantizers import PipelineQuantizationConfig
            squeeze = PipelineQuantizationConfig(quant_mapping={"transformer": DiffusersQuanto(weights_dtype="int8")})
            self.pipe = Flux2KleinPipeline.from_pretrained(str(WEIGHTS), text_encoder=self.load_text(),
                                                           torch_dtype=torch.bfloat16, quantization_config=squeeze)
            self.pipe.enable_model_cpu_offload()
        self.read = (None, None)   # (description, its reading)

    def reading(self, prompt):
        """The text model's reading of a description; the last one is reused."""
        if self.read[0] != prompt:
            step("Reading the description")
            torch, pipe = self.torch, self.pipe
            if self.mode == "resident":
                # hand back memory the last picture left reserved first: going over the card's 16 GB even for a
                # moment makes Windows move part of the picture model to system memory, and it stays slow
                torch.cuda.empty_cache()
                pipe.text_encoder = self.load_text().to("cuda")
            with torch.inference_mode():
                embeds = pipe.encode_prompt(prompt, device=torch.device("cuda"))[0]
            if self.mode == "resident":
                pipe.text_encoder = None  # dropped: kept in system memory it made Windows page (minutes a picture)
                import gc
                gc.collect()
                torch.cuda.empty_cache()
            self.read = (prompt, embeds)
        return self.read[1]

    def paint(self, r):
        from PIL import Image

        torch, pipe = self.torch, self.pipe
        seed = r["seed"] if r.get("seed") is not None else random.randrange(1, 2**31 - 1)
        width, height = int(r.get("width", 1024)) // 16 * 16, int(r.get("height", 1024)) // 16 * 16
        steps = int(r.get("steps", 4))

        def progress(pipeline, i, t, kwargs):
            step(f"Painting: step {i + 1} of {steps}")
            return kwargs

        options = dict(prompt_embeds=self.reading(r["prompt"]), width=width, height=height,
                       num_inference_steps=steps, guidance_scale=1.0, output_type="latent",
                       generator=torch.Generator("cpu").manual_seed(seed), callback_on_step_end=progress)
        refs = [Image.open(p).convert("RGB") for p in r.get("refs", [])]
        if refs:
            options["image"] = refs
        with torch.inference_mode():
            latents = pipe(**options).images
            step("Finishing the picture")
            # decoded here rather than inside the pipeline: measured steady at ~6 s on an RX 7800 XT
            decoded = pipe.vae.decode(latents.to(pipe.vae.device), return_dict=False)[0]
            image = pipe.image_processor.postprocess(decoded, output_type="pil")[0]
        del latents, decoded
        torch.cuda.empty_cache()
        if r.get("tile"):
            image = tileable(image)
        Path(r["out"]).parent.mkdir(parents=True, exist_ok=True)
        image.save(r["out"])
        return {"ok": True, "seed": seed, "width": image.width, "height": image.height, "mode": self.mode}


def main():
    try:
        painter = Painter()
    except Exception as e:
        reply({"ready": False, "error": f"{type(e).__name__}: {e}"[:800]})
        return
    reply({"ready": True, "mode": painter.mode})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            reply(painter.paint(json.loads(line)))
        except Exception as e:
            painter.torch.cuda.empty_cache()
            reply({"ok": False, "error": f"{type(e).__name__}: {e}"[:800]})


if __name__ == "__main__":
    main()
