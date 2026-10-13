"""Cut-out worker (gamekit engine "cutout"). gamekit starts it in the engine's own Python and talks to it
over stdin/stdout: one JSON request a line in, one "@@"-prefixed JSON reply a line out, plus
@@{"step": "..."} lines while it works.

The model is BiRefNet lite (Peng Zheng et al., MIT), as ONNX: it finds the subject of a picture and gives
everything else a transparent background, soft edges included. It runs on the processor (about 10 s a
picture), so it doesn't need the graphics card and can stay loaded beside the picture model.

Request: {"in", "out"}
Reply:   {"ok": true, "width", "height"}
"""
import json
import sys
from pathlib import Path

REPO = "onnx-community/BiRefNet_lite-ONNX"
SIDE = 1024  # the model looks at the picture at 1024x1024
MEAN, STD = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)


def reply(obj):
    sys.stdout.write("@@" + json.dumps(obj) + "\n")
    sys.stdout.flush()


def step(text):
    reply({"step": text})


def cut(session, path_in, path_out):
    import numpy as np
    from PIL import Image

    with Image.open(path_in) as opened:
        image = opened.convert("RGB")
    x = np.asarray(image.resize((SIDE, SIDE), Image.Resampling.BILINEAR), dtype=np.float32) / 255
    x = ((x - MEAN) / STD).transpose(2, 0, 1)[None].astype(np.float32)
    logits = session.run(None, {session.get_inputs()[0].name: x})[-1][0, 0]
    mask = 1 / (1 + np.exp(-logits))
    alpha = Image.fromarray((mask * 255).round().astype(np.uint8)).resize(image.size, Image.Resampling.BILINEAR)
    image.putalpha(alpha)
    Path(path_out).parent.mkdir(parents=True, exist_ok=True)
    image.save(path_out)
    return image.size


def main():
    try:
        import onnxruntime
        from huggingface_hub import hf_hub_download

        step("Loading the cut-out model")
        try:
            model = hf_hub_download(REPO, "onnx/model.onnx", local_files_only=True)
        except Exception:
            step("Downloading the cut-out model (about 210 MB, first time only)")
            model = hf_hub_download(REPO, "onnx/model.onnx")
        # without its memory pool: with it, every other cut-out took 3x as long on a 16 GB PC (~8 s steady without)
        options = onnxruntime.SessionOptions()
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        session = onnxruntime.InferenceSession(model, options, providers=["CPUExecutionProvider"])
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
            step("Cutting out the subject")
            width, height = cut(session, r["in"], r["out"])
            reply({"ok": True, "width": width, "height": height})
        except Exception as e:
            reply({"ok": False, "error": f"{type(e).__name__}: {e}"[:800]})


if __name__ == "__main__":
    main()
