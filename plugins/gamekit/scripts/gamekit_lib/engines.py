"""Engines: local AI models (pictures now; music, sounds, voices, 3D later), each in its own Python.

An engine is a Python environment under the engines folder (%LOCALAPPDATA%\\gamekit\\engines on
Windows, ~/.local/share/gamekit/engines elsewhere; GAMEKIT_ENGINES overrides) with PyTorch for this
PC's graphics card, plus a worker script from plugins/gamekit/engines/. Model files download into
engines/models the first time an engine loads them, so nothing big lives in the plugin or the game.

A worker is a long-running process: one JSON request per line on stdin, one reply per line on stdout,
prefixed "@@". `{"step": "..."}` lines report progress; the first real reply says {"ready": true}.
Only one worker runs at a time, since they share the graphics card's memory.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

WORKERS = Path(__file__).resolve().parent.parent.parent / "engines"
PYTHON = "3.12"  # AMD's PyTorch for Windows only comes for Python 3.12
ROCM_WINDOWS = "https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1"
ROCM_WINDOWS_PACKAGES = [
    f"{ROCM_WINDOWS}/rocm_sdk_core-7.2.1-py3-none-win_amd64.whl",
    f"{ROCM_WINDOWS}/rocm_sdk_devel-7.2.1-py3-none-win_amd64.whl",
    f"{ROCM_WINDOWS}/rocm_sdk_libraries_custom-7.2.1-py3-none-win_amd64.whl",
    f"{ROCM_WINDOWS}/rocm-7.2.1.tar.gz",
]
ROCM_WINDOWS_TORCH = [
    f"{ROCM_WINDOWS}/torch-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl",
    f"{ROCM_WINDOWS}/torchaudio-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl",
    f"{ROCM_WINDOWS}/torchvision-0.24.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl",
]
CUDA_INDEX = "https://download.pytorch.org/whl/cu128"


@dataclass
class Engine:
    name: str
    title: str
    worker: str                 # file in plugins/gamekit/engines/
    packages: list[str]         # pip requirements besides PyTorch (versions known to work together)
    model: str                  # what it downloads on first use, for people
    license: str
    model_dirs: list[str] = field(default_factory=list)  # folders under engines/models it fills
    code: tuple[str, str] | None = None     # (git URL, commit): the model's own code, kept in engines/code/<name>
    requirements: dict[str, str] = field(default_factory=dict)  # PyTorch kind ("rocm"/"cuda"/"cpu"/"*") -> file in code
    env: dict[str, str] = field(default_factory=dict)  # extra settings for its worker
    install_code: bool = False  # pip-install the code itself without its dependencies (they pin CUDA PyTorch)
    note: str = ""              # anything the person must do first, e.g. accept a license
    hf_repos: list[str] = field(default_factory=list)  # models it loads through the Hugging Face cache (engines/hf)


ENGINES = {
    "picture": Engine(
        "picture", "Pictures", "picture_worker.py",
        ["diffusers==0.41.0", "transformers==5.19.0", "accelerate==1.15.0", "optimum-quanto==0.2.7",
         "huggingface_hub", "safetensors", "sentencepiece", "numpy", "pillow"],
        "FLUX.2 klein 4B by Black Forest Labs, about 16 GB on first use", "Apache 2.0",
        ["FLUX.2-klein-4B"]),
    "music": Engine(
        "music", "Music", "music_worker.py", ["soundfile", "loguru", "pytorch_wavelets", "PyWavelets"],
        "ACE-Step 1.5 turbo (+ optional 1.7B planner), about 10 GB on first use", "MIT",
        ["acestep"],
        code=("https://github.com/ace-step/ACE-Step-1.5.git", "ca1e85fe9430179831e6bc6be790c332190a3866"),
        requirements={"rocm": "requirements-rocm.txt", "*": "requirements.txt"},
        # from ACE-Step's own ROCm launchers: plain PyTorch planner (no flash-attn), no torch.compile
        env={"ACESTEP_LM_BACKEND": "pt", "TORCH_COMPILE_BACKEND": "eager", "TOKENIZERS_PARALLELISM": "false"}),
    "voice": Engine(
        "voice", "Voices", "voice_worker.py", ["qwen-tts==0.1.1", "soundfile"],
        "Qwen3-TTS 1.7B VoiceDesign by Alibaba Qwen, about 4 GB on first use", "Apache 2.0",
        ["Qwen3-TTS-12Hz-1.7B-VoiceDesign"]),
    "sound": Engine(
        "sound", "Sounds", "sound_worker.py",
        ["einops-exts>=0.0.4", "einops>=0.8.2", "huggingface-hub>=1.7.1", "numpy", "packaging", "safetensors",
         "soundfile", "tqdm", "transformers==5.8.0"],
        "Stable Audio 3 Small SFX by Stability AI, about 3.5 GB on first use",
        "Stability AI Community License (free, also commercially under $1M a year in revenue)",
        code=("https://github.com/Stability-AI/stable-audio-3.git", "af60ef53ff9b2074719ee23d89c44aa433d0c55b"),
        install_code=True, hf_repos=["stabilityai/stable-audio-3-small-sfx"],
        note="The model is gated: accept its license once at huggingface.co/stabilityai/stable-audio-3-small-sfx, "
             "then sign in on this PC (`hf auth login`, a Read token) so the first sound can download it."),
}


class EngineError(Exception):
    pass


# --- places --------------------------------------------------------------------------------------

def home() -> Path:
    configured = os.environ.get("GAMEKIT_ENGINES")
    if configured:
        return Path(configured)
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "gamekit" / "engines"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "gamekit" / "engines"


def get(name: str) -> Engine:
    if name not in ENGINES:
        raise EngineError(f"unknown engine {name!r}; there are: {', '.join(ENGINES)}")
    return ENGINES[name]


def venv(engine: Engine) -> Path:
    return home() / engine.name


def python(engine: Engine) -> Path:
    folder = venv(engine)
    return folder / "Scripts" / "python.exe" if sys.platform == "win32" else folder / "bin" / "python"


def models_dir() -> Path:
    return home() / "models"


def code_dir(engine: Engine) -> Path:
    """Where an engine's own code (a git checkout) lives, if it has any."""
    return home() / "code" / engine.name


def is_installed(engine: Engine) -> bool:
    return python(engine).exists() and (venv(engine) / "gamekit-engine.json").exists()


def has_model(engine: Engine) -> bool:
    folders = [models_dir() / d for d in engine.model_dirs]
    folders += [home() / "hf" / "hub" / ("models--" + repo.replace("/", "--")) / "snapshots" for repo in engine.hf_repos]
    return all(folder.is_dir() and any(folder.iterdir()) for folder in folders)


def status(engine: Engine) -> dict:
    info = {}
    marker = venv(engine) / "gamekit-engine.json"
    if marker.exists():
        try:
            info = json.loads(marker.read_text(encoding="utf-8"))
        except ValueError:
            info = {}
    return {"name": engine.name, "title": engine.title, "installed": is_installed(engine), "model": engine.model,
            "license": engine.license, "model_ready": has_model(engine), "torch": info.get("torch", ""),
            "note": engine.note,
            "folder": str(venv(engine))}


# --- setting up ----------------------------------------------------------------------------------

def find_uv() -> str:
    """uv (Astral's Python installer): $GAMEKIT_UV, then PATH."""
    configured = os.environ.get("GAMEKIT_UV")
    if configured:
        if Path(configured).exists():
            return configured
        raise EngineError(f"GAMEKIT_UV points to {configured}, which doesn't exist")
    found = shutil.which("uv")
    if found:
        return found
    raise EngineError("uv not found. Install it (Windows: `winget install astral-sh.uv`; others: "
                      "https://docs.astral.sh/uv/), or set GAMEKIT_UV to uv's full path.")


def graphics() -> str:
    """Which PyTorch this PC needs: "rocm" (AMD on Windows), "cuda" (NVIDIA) or "cpu". GAMEKIT_TORCH overrides."""
    forced = os.environ.get("GAMEKIT_TORCH", "").lower()
    if forced in ("rocm", "cuda", "cpu"):
        return forced
    names = ""
    if sys.platform == "win32":
        try:
            names = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name"],
                capture_output=True, text=True, timeout=30).stdout
        except (OSError, subprocess.TimeoutExpired):
            names = ""
    elif shutil.which("nvidia-smi"):
        names = "NVIDIA"
    if "NVIDIA" in names.upper():
        return "cuda"
    if sys.platform == "win32" and ("RADEON" in names.upper() or "AMD" in names.upper()):
        return "rocm"
    return "cpu"


def torch_commands(uv: str, py: str, kind: str) -> list[list[str]]:
    """The uv commands that install PyTorch of `kind` into the environment whose python is `py`."""
    pip = [uv, "pip", "install", "--python", py]
    if kind == "rocm":
        if sys.platform != "win32":
            raise EngineError("AMD graphics on Linux: set GAMEKIT_TORCH=cpu, or install ROCm PyTorch by hand")
        return [pip + ROCM_WINDOWS_PACKAGES, pip + ROCM_WINDOWS_TORCH]
    if kind == "cuda":
        return [pip + ["--index-url", CUDA_INDEX, "torch", "torchvision", "torchaudio"]]
    return [pip + ["torch", "torchvision", "torchaudio"]]


def setup(name: str, run: Callable[[list[str]], None] | None = None) -> Iterator[str]:
    """Creates (or repairs) an engine's environment, yielding a line of progress per step. `run` runs
    one command (tests replace it); by default it raises EngineError when the command fails."""
    engine = get(name)
    run = run or _run
    uv = find_uv()
    folder = venv(engine)
    kind = graphics()
    yield f"{engine.title}: PyTorch for {dict(rocm='an AMD graphics card', cuda='an NVIDIA graphics card', cpu='the processor (slow)')[kind]}"
    if not python(engine).exists():
        yield f"Making its Python {PYTHON} environment in {folder}"
        run([uv, "venv", "--python", PYTHON, str(folder)])
    py = str(python(engine))
    if engine.code:
        url, commit = engine.code
        code = code_dir(engine)
        git = shutil.which("git")
        if not git:
            raise EngineError("git not found: install Git (Windows: `winget install Git.Git`) and try again")
        if not (code / ".git").exists():
            yield f"Downloading the model's code from {url}"
            code.parent.mkdir(parents=True, exist_ok=True)
            run([git, "clone", "--quiet", url, str(code)])
        yield f"Using its code at {commit[:7]}"
        run([git, "-C", str(code), "fetch", "--quiet", "origin"])
        run([git, "-C", str(code), "checkout", "--quiet", "--force", commit])
    yield "Installing PyTorch (a few GB; several minutes the first time)"
    for command in torch_commands(uv, py, kind):
        run(command)
    yield "Installing the model's libraries"
    requirements = engine.requirements.get(kind) or engine.requirements.get("*")
    if requirements:
        run([uv, "pip", "install", "--python", py, "-r", str(code_dir(engine) / requirements)])
    run([uv, "pip", "install", "--python", py, *engine.packages])
    if engine.install_code:
        run([uv, "pip", "install", "--python", py, "--no-deps", "-e", str(code_dir(engine))])
    yield "Checking that it works"
    check = subprocess.run([py, "-c", "import torch, json; print(json.dumps([torch.__version__, torch.cuda.is_available()]))"],
                           capture_output=True, text=True, timeout=600)
    if check.returncode != 0:
        raise EngineError(f"PyTorch doesn't start: {check.stderr.strip()[-600:]}")
    version, gpu = json.loads(check.stdout.strip().splitlines()[-1])
    (folder / "gamekit-engine.json").write_text(
        json.dumps({"engine": name, "torch": version, "gpu": gpu, "kind": kind}, indent=2), encoding="utf-8")
    yield f"Ready: PyTorch {version}, " + ("using the graphics card" if gpu else "on the processor (no graphics card found)")


def remove(name: str) -> Path:
    """Deletes an engine's environment (not its downloaded model files)."""
    engine = get(name)
    stop_all()
    folder = venv(engine)
    for place in (folder, code_dir(engine)):
        if place.exists():
            shutil.rmtree(place, onerror=_writable)
    return folder


def _writable(function: Callable, path: str, info: object) -> None:
    """git marks some of its files read-only, which stops Windows deleting them: clear that and retry."""
    os.chmod(path, 0o700)
    function(path)


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise EngineError(f"{Path(command[0]).name} {command[1]} failed:\n{(result.stderr or result.stdout).strip()[-1500:]}")


# --- running workers -----------------------------------------------------------------------------

def worker_env(engine: Engine | None = None) -> dict[str, str]:
    extra = dict(engine.env, GAMEKIT_ENGINE_CODE=str(code_dir(engine))) if engine else {}
    return dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", **extra,
                GAMEKIT_MODELS=str(models_dir()), HF_HOME=str(home() / "hf"),
                HF_HUB_DISABLE_SYMLINKS_WARNING="1", HF_HUB_DISABLE_PROGRESS_BARS="1",
                TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL="1",  # AMD's fast attention: ~4x faster on an RX 7800 XT
                MIOPEN_FIND_MODE="FAST")  # AMD: skip benchmarking every new image size (minutes the first time)


class Worker:
    """One engine's worker process. ask() sends a request and waits for its reply, passing
    {"step": ...} progress lines to `on_step`."""

    def __init__(self, engine: Engine, command: list[str] | None = None) -> None:
        self.engine = engine
        self.command = command or [str(python(engine)), "-u", str(WORKERS / engine.worker)]
        self.proc: subprocess.Popen | None = None
        self.log = None
        self.lock = threading.Lock()

    @property
    def log_path(self) -> Path:
        return home() / "logs" / f"{self.engine.name}.log"

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, on_step: Callable[[str], None] = lambda s: None) -> None:
        if self.running():
            return
        if self.command[0] == str(python(self.engine)) and not is_installed(self.engine):
            raise EngineError(f"the {self.engine.name} engine isn't set up yet: run `gamekit engines setup {self.engine.name}`")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._close_log()
        self.log = open(self.log_path, "w", encoding="utf-8")
        on_step(f"Starting the {self.engine.title.lower()} model")
        work = home() / "work" / self.engine.name  # libraries write caches where they run: not into the plugin
        work.mkdir(parents=True, exist_ok=True)
        self.proc = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
                                     text=True, encoding="utf-8", errors="replace", env=worker_env(self.engine),
                                     cwd=str(work))
        hello = self._reply(on_step)
        if not hello.get("ready"):
            self.stop()
            raise EngineError(hello.get("error") or f"the {self.engine.name} model didn't load")

    def ask(self, request: dict, on_step: Callable[[str], None] = lambda s: None) -> dict:
        with self.lock:
            self.start(on_step)
            assert self.proc and self.proc.stdin
            self.proc.stdin.write(json.dumps(request) + "\n")
            self.proc.stdin.flush()
            answer = self._reply(on_step)
        if not answer.get("ok"):
            raise EngineError(answer.get("error") or f"the {self.engine.name} model failed")
        return answer

    def _reply(self, on_step: Callable[[str], None]) -> dict:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            if not line.startswith("@@"):
                continue
            message = json.loads(line[2:])
            if "step" in message and len(message) == 1:
                on_step(str(message["step"]))
                continue
            return message
        code = self.proc.wait()
        self.proc = None
        self._close_log()
        raise EngineError(f"the {self.engine.name} model stopped unexpectedly (exit code {code}); see {self.log_path}")

    def stop(self) -> None:
        if self.proc is not None:
            if self.proc.poll() is None:
                self.proc.kill()
                self.proc.wait()
            for pipe in (self.proc.stdin, self.proc.stdout):
                if pipe:
                    pipe.close()
            self.proc = None
        self._close_log()

    def _close_log(self) -> None:
        if self.log is not None:
            self.log.close()
            self.log = None


_workers: dict[str, Worker] = {}


def worker(name: str) -> Worker:
    """The engine's worker, stopping any other engine first (one model on the graphics card at a time)."""
    for other, w in list(_workers.items()):
        if other != name and w.running():
            w.stop()
    if name not in _workers:
        _workers[name] = Worker(get(name))
    return _workers[name]


def stop_all() -> None:
    for w in _workers.values():
        w.stop()
