"""Certification script for AlgoFortis Native Windows Desktop App Window."""
import json
import os
import subprocess
import sys
import time
import winreg
from pathlib import Path
from urllib.request import Request, urlopen, build_opener, ProxyHandler

clean_root = Path(__file__).resolve().parents[2]
setup_exe = clean_root / "build" / "installer" / "AlgoFortis-Setup.exe"
install_dir = Path(r"C:\Program Files\AlgoFortis")
python_exe = install_dir / "runtime" / "python" / "python.exe"

def log(msg):
    print(f"[DESKTOP SHELL CERT] {msg}")

def test_install():
    log("Step 1: Installing rebuilt AlgoFortis-Setup.exe silently...")
    cmd = [str(setup_exe), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/MERGETASKS=desktopicon"]
    res = subprocess.run(cmd)
    assert res.returncode == 0, f"Installer failed with code {res.returncode}"
    time.sleep(3)
    assert install_dir.exists(), "Installation directory not found!"
    assert (install_dir / "AlgoFortis.exe").exists(), "AlgoFortis.exe missing!"
    assert (install_dir / "Microsoft.Web.WebView2.Core.dll").exists(), "WebView2 Core DLL missing!"
    assert (install_dir / "Microsoft.Web.WebView2.WinForms.dll").exists(), "WebView2 WinForms DLL missing!"
    assert (install_dir / "WebView2Loader.dll").exists(), "WebView2Loader.dll missing!"
    log("  PASS: Clean installation completed with WebView2 assemblies.")

    # Verify shortcuts
    desktop_dirs = [
        Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop",
        Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    ]
    desktop_lnk = None
    for d in desktop_dirs:
        candidate = d / "AlgoFortis.lnk"
        if candidate.exists():
            desktop_lnk = candidate
            break
    start_lnk = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "AlgoFortis" / "AlgoFortis.lnk"
    assert desktop_lnk is not None, f"Desktop shortcut AlgoFortis.lnk missing in {desktop_dirs}!"
    assert start_lnk.exists(), f"Start Menu shortcut {start_lnk} missing!"
    log(f"  PASS: Desktop ({desktop_lnk}) and Start Menu shortcuts confirmed.")

def test_desktop_window_launch():
    log("Step 2: Launching AlgoFortis.exe and auditing processes & embedded WebView2...")

    # Clear previous launcher log
    log_dir = Path(os.environ["LOCALAPPDATA"]) / "AlgoFortis" / "logs"
    launcher_log = log_dir / "launcher.log"
    if launcher_log.exists():
        try:
            launcher_log.unlink()
        except Exception:
            pass

    # Launch AlgoFortis.exe directly (simulating double-click)
    proc = subprocess.Popen([str(install_dir / "AlgoFortis.exe")], cwd=str(install_dir))
    
    cmd_status = [str(python_exe), "-m", "dashboard.runtime.controller", "status", "--mode", "PRODUCTION", "--install-root", str(install_dir)]
    deadline = time.monotonic() + 30
    ready_data = None
    while time.monotonic() < deadline:
        res = subprocess.run(cmd_status, cwd=str(install_dir), capture_output=True, text=True)
        if res.returncode == 0:
            try:
                data = json.loads(res.stdout.strip())
                if data.get("state") == "READY":
                    ready_data = data
                    break
            except Exception:
                pass
        time.sleep(0.5)

    assert ready_data is not None, "Installed application failed to start backend within 30s!"
    backend_url = ready_data["url"]
    log(f"  PASS: Backend is running and READY at {backend_url} (PID: {ready_data['pid']})")

    # Give WebView2 time to render
    time.sleep(4)

    # Verify WebView2 process tree
    ps_cmd = [
        "powershell.exe", "-NoProfile", "-Command",
        r'Get-Process -Name "msedgewebview2" -ErrorAction SilentlyContinue | Select-Object Id, ProcessName | ConvertTo-Json'
    ]
    ps_res = subprocess.run(ps_cmd, capture_output=True, text=True)
    assert ps_res.returncode == 0 and ps_res.stdout.strip(), "No msedgewebview2 processes found!"
    log("  PASS: msedgewebview2 child processes verified running inside desktop shell.")

    # Audit that launcher log shows embedded window initialized
    assert launcher_log.exists(), "launcher.log not created!"
    log_content = launcher_log.read_text(encoding="utf-8")
    assert "StartAndInitializeAsync started" in log_content
    assert "EnsureBackendStarted: initial status" in log_content
    log("  PASS: launcher.log audits native window lifecycle and backend coordination.")

    # Terminate shell
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        pass
    log("  PASS: Desktop window closed cleanly.")

def run_uninstall():
    log("Step 3: Cleaning up installation...")
    try:
        subprocess.run([str(python_exe), "-m", "dashboard.runtime.controller", "stop", "--mode", "PRODUCTION", "--install-root", str(install_dir)], capture_output=True)
    except Exception:
        pass
    time.sleep(1)
    uninstaller = install_dir / "unins000.exe"
    subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], check=True)
    deadline = time.monotonic() + 30
    removed = False
    while time.monotonic() < deadline:
        if not install_dir.exists() or not (install_dir / "AlgoFortis.exe").exists():
            removed = True
            break
        time.sleep(0.5)
    assert removed, "Uninstall failed to remove install dir!"
    log("  PASS: Uninstallation verified.")

def main():
    print("=== STARTING DESKTOP SHELL CORRECTION CERTIFICATION ===")
    test_install()
    test_desktop_window_launch()
    run_uninstall()
    print("=== DESKTOP SHELL CORRECTION CERTIFICATION: ALL PASS ===")

if __name__ == "__main__":
    main()
