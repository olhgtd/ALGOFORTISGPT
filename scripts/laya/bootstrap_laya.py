from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import sys


SOURCE_REPOSITORY = "https://github.com/NandhaKishorM/laya.git"
SOURCE_COMMIT = "9d955671415fc19f069b9cc998928075c1f255ec"
MODEL_REPOSITORY = "convaiinnovations/laya"
MODEL_REVISION = "00c37c405e3c3ad73ee070227614c89cda06b99e"
MODEL_SHA256 = "891102d372688fc2a094dac56a384bc537b87c63f21f9f3dac0be2b7cbc8d86c"

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "third_party" / "laya" / "upstream"
MODEL_DIR = ROOT / "models" / "laya" / "original"


def _run(*args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return completed.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_source_checkout() -> None:
    SOURCE_DIR.parent.mkdir(parents=True, exist_ok=True)
    if not (SOURCE_DIR / ".git").is_dir():
        if SOURCE_DIR.exists() and any(SOURCE_DIR.iterdir()):
            raise RuntimeError(f"refusing to overwrite non-git directory: {SOURCE_DIR}")
        _run("git", "clone", "--filter=blob:none", SOURCE_REPOSITORY, str(SOURCE_DIR))
    _run("git", "fetch", "--depth", "1", "origin", SOURCE_COMMIT, cwd=SOURCE_DIR)
    _run("git", "checkout", "--detach", SOURCE_COMMIT, cwd=SOURCE_DIR)
    actual = _run("git", "rev-parse", "HEAD", cwd=SOURCE_DIR)
    if actual != SOURCE_COMMIT:
        raise RuntimeError(f"unexpected Laya source commit: {actual}")


def ensure_model_checkpoint() -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "huggingface_hub is required; install the AlgoFortis/Laya runtime dependencies first"
        ) from exc

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=MODEL_REPOSITORY,
        revision=MODEL_REVISION,
        local_dir=str(MODEL_DIR),
        allow_patterns=[
            "model.safetensors",
            "encoder/*",
            "tokenizer/*",
            "rl_agent_config.json",
            "README.md",
        ],
    )
    model_file = MODEL_DIR / "model.safetensors"
    if not model_file.is_file():
        raise RuntimeError(f"Laya model file is missing after download: {model_file}")
    actual = _sha256(model_file)
    if actual != MODEL_SHA256:
        raise RuntimeError(
            "Laya model SHA-256 mismatch: "
            f"expected {MODEL_SHA256}, got {actual}"
        )


def install_runtime_editable() -> None:
    _run(sys.executable, "-m", "pip", "install", "-e", str(SOURCE_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Populate AlgoFortis project-local Laya source and model workspace."
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="download and verify source/model but do not pip-install the local runtime",
    )
    args = parser.parse_args()

    ensure_source_checkout()
    ensure_model_checkpoint()
    if not args.skip_install:
        install_runtime_editable()

    print("Laya workspace ready")
    print(f"source: {SOURCE_DIR}")
    print(f"model : {MODEL_DIR}")
    print(f"sha256: {MODEL_SHA256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
