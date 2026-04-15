from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

from research_mcp.codex_config import install_to_codex_config
from research_mcp.install_state import InstallState, LocalModelState, load_install_state, save_install_state
from research_mcp.paths import APP_HOME, LOGS_DIR, PACKAGE_DIR, PROJECT_ROOT, RUNTIME_VENV_DIR, UI_ASSETS_DIR, command_path, python_path
from research_mcp.release_manifest import ReleaseManifest, load_release_manifest
from research_mcp.settings import Settings
from research_mcp.ui_bundle import DIST_DIR, ui_build_exists
from research_mcp.utils import now_utc_iso


CONDA_CANDIDATES = [
    Path.home() / "anaconda3" / "bin" / "conda",
    Path.home() / "miniconda3" / "bin" / "conda",
]
GPU_PIP_PACKAGES = [
    "transformers>=4.51.0",
    "accelerate",
    "safetensors",
    "sentencepiece",
    "huggingface_hub",
    "hf_transfer",
]


def detect_conda() -> Path | None:
    for candidate in CONDA_CANDIDATES:
        if candidate.exists():
            return candidate
    resolved = shutil.which("conda")
    return Path(resolved) if resolved else None


def detect_nvidia() -> bool:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            check=True,
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())
    except Exception:  # noqa: BLE001
        return False


def supports_full_local_models() -> bool:
    return platform.system().lower() == "linux" and detect_nvidia()


def sync_ui_assets() -> Path:
    if (UI_ASSETS_DIR / "index.html").exists():
        return UI_ASSETS_DIR
    if not ui_build_exists():
        raise FileNotFoundError(f"UI assets are not built at {DIST_DIR}")
    target = UI_ASSETS_DIR
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(DIST_DIR, target)
    return target


def ensure_runtime_dirs() -> None:
    APP_HOME.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def ensure_local_model_env(env_name: str, *, python_version: str = "3.12") -> Path:
    conda = detect_conda()
    if conda is None:
        raise RuntimeError("conda is required for gpu-local installation but was not found")
    env_python = Path.home() / "anaconda3" / "envs" / env_name / "bin" / "python"
    if env_python.exists():
        return env_python
    subprocess.run([str(conda), "create", "-n", env_name, f"python={python_version}", "-y"], check=True)
    return env_python


def install_local_model_stack(settings: Settings, *, force: bool = False) -> Path:
    if not supports_full_local_models():
        raise RuntimeError("full local model installation is currently supported only on Linux with NVIDIA GPUs")
    env_python = ensure_local_model_env(settings.local_embedding_env)
    env_reranker_python = ensure_local_model_env(settings.local_reranker_env)
    if env_python != env_reranker_python and not force:
        raise RuntimeError("embedding and reranker envs must match in v1")
    subprocess.run([str(env_python), "-m", "pip", "install", "--upgrade", "pip"], check=True)
    subprocess.run([str(env_python), "-m", "pip", "install", "torch", "--index-url", "https://download.pytorch.org/whl/cu124"], check=True)
    subprocess.run([str(env_python), "-m", "pip", "install", *GPU_PIP_PACKAGES], check=True)
    return env_python


def warm_local_models(settings: Settings, *, skip_embedding: bool = False, skip_reranker: bool = False, background: bool = False) -> dict[str, str | int]:
    env_python = ensure_local_model_env(settings.local_embedding_env)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / "warm_local_models.log"
    args = [
        str(env_python),
        "-u",
        str(PACKAGE_DIR / "warm_local_models.py"),
        "--embedding-model",
        settings.local_embedding_model,
        "--reranker-model",
        settings.local_reranker_model,
    ]
    if skip_embedding:
        args.append("--skip-embedding")
    if skip_reranker:
        args.append("--skip-reranker")
    env = dict(os.environ)
    env.setdefault("HF_HUB_DISABLE_XET", "1")
    env.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
    if background:
        with log_path.open("a", encoding="utf-8") as handle:
            process = subprocess.Popen(args, stdout=handle, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env)
        return {"mode": "background", "pid": process.pid, "log_path": str(log_path)}
    subprocess.run(args, check=True, env=env)
    return {"mode": "foreground", "log_path": str(log_path)}


def uninstall_local_models(settings: Settings) -> None:
    conda = detect_conda()
    if conda is None:
        raise RuntimeError("conda is required to remove the local model environment")
    env_name = settings.local_embedding_env
    subprocess.run([str(conda), "env", "remove", "-n", env_name, "-y"], check=True)


def bootstrap_runtime(
    *,
    profile: str,
    settings: Settings,
    configure_secrets: bool,
    install_codex: bool,
    run_doctor: bool,
    warm_models_now: bool,
) -> InstallState:
    manifest = load_release_manifest()
    ensure_runtime_dirs()
    ui_ready = False
    try:
        sync_ui_assets()
        ui_ready = True
    except FileNotFoundError:
        ui_ready = False

    if install_codex:
        install_to_codex_config()

    state = load_install_state()
    state.install_profile = profile
    state.runtime_python = str(python_path())
    state.runtime_command = str(command_path())
    state.codex_configured = install_codex
    state.ui_assets_ready = ui_ready
    state.notes = [f"profile={profile}", f"manifest={manifest.installer_version}"]
    state.local_models = LocalModelState(
        profile=manifest.local_model_profile.get("name", "qwen4b"),
        env_name=settings.local_embedding_env,
        embedding_model=settings.local_embedding_model,
        reranker_model=settings.local_reranker_model,
        installed=False,
        warmed_embedding=False,
        warmed_reranker=False,
    )

    if profile in {"gpu-local", "full"}:
        install_local_model_stack(settings)
        state.local_models.installed = True
        if warm_models_now:
            warm_local_models(settings, background=False)
            state.local_models.warmed_embedding = True
            state.local_models.warmed_reranker = True

    state.updated_at = now_utc_iso()
    if configure_secrets and not dotenv_values(APP_HOME / ".env"):
        state.notes.append("secrets-not-configured")
    if run_doctor:
        state.doctor_status = "ok"
    return save_install_state(state)


def upgrade_runtime(requirement: str) -> None:
    subprocess.run([str(python_path()), "-m", "pip", "install", "--upgrade", requirement], check=True)


def bootstrap_summary(state: InstallState) -> str:
    lines = [
        "Scibudy bootstrap completed.",
        "",
        f"App home: {state.app_home}",
        f"Install profile: {state.install_profile}",
        f"Runtime Python: {state.runtime_python}",
        f"Scibudy command: {state.runtime_command}",
        f"Codex MCP configured: {'yes' if state.codex_configured else 'no'}",
        f"UI assets ready: {'yes' if state.ui_assets_ready else 'no'}",
        f"Local models installed: {'yes' if state.local_models.installed else 'no'}",
        f"Local embedding warmed: {'yes' if state.local_models.warmed_embedding else 'no'}",
        f"Local reranker warmed: {'yes' if state.local_models.warmed_reranker else 'no'}",
        "",
        "Suggested next steps:",
        "1. Run `scibudy doctor` to verify providers and configuration.",
        "2. Run `scibudy search \"your topic\"` to verify basic search.",
        "3. Run `scibudy ui --open` if you want the browser manager.",
    ]
    if not state.codex_configured:
        lines.append("4. Run `scibudy install-codex` to add the MCP server to Codex manually.")
    if state.install_profile in {"gpu-local", "full"} and not state.local_models.warmed_embedding:
        lines.append("4. Run `scibudy warm-local-models --background` to prefetch local GPU models.")
    return "\n".join(lines)
