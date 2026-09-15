"""Windowless launcher backward-compatibility entry invoking native AlgoFortis desktop application."""
import subprocess
import ctypes
from pathlib import Path


if __name__ == "__main__":
    try:
        install_root = Path(__file__).resolve().parent
        exe = install_root / "AlgoFortis.exe"
        if not exe.is_file():
            exe = install_root / "SentinelX.exe"
        if exe.is_file():
            subprocess.Popen([str(exe)], cwd=str(install_root))
        else:
            from dashboard.runtime.controller import RuntimeController
            from dashboard.runtime.paths import RuntimePaths, RuntimeMode
            runtime = RuntimeController(RuntimePaths.resolve(RuntimeMode.PRODUCTION, install_root=install_root))
            info = runtime.start()
            if info.get("state") != "READY":
                raise RuntimeError("Failed to start runtime controller")
    except Exception as exc:
        ctypes.windll.user32.MessageBoxW(None, f"AlgoFortis is unavailable.\n{exc}", "AlgoFortis", 0x10)
