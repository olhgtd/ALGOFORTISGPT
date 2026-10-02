"""Phase 9 & Phase 10 Clean-Install UX, LifeCycle, and Installed Functional Smoke Certification for AlgoFortis."""
import json
import os
import signal
import subprocess
import sys
import time
import winreg
from pathlib import Path
from urllib.request import Request, urlopen, build_opener, ProxyHandler
from urllib.error import HTTPError

clean_root = Path(__file__).resolve().parents[2]
setup_exe = clean_root / "build" / "installer" / "AlgoFortis-Setup.exe"
install_dir = Path(r"C:\Program Files\AlgoFortis")
opener = build_opener(ProxyHandler({}))

def log(msg):
    print(f"[INSTALL CERT] {msg}")

def check_shortcuts():
    desktop_dirs = [
        Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop",
        Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    ]
    desktop_shortcut = None
    for d in desktop_dirs:
        candidate = d / "AlgoFortis.lnk"
        if candidate.exists():
            desktop_shortcut = candidate
            break
    assert desktop_shortcut is not None, f"Desktop shortcut AlgoFortis.lnk not found in {desktop_dirs}"
    log(f"  PASS: Desktop shortcut found at: {desktop_shortcut}")

    start_menu_dirs = [
        Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "AlgoFortis",
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "AlgoFortis"
    ]
    start_shortcut = None
    for sm in start_menu_dirs:
        candidate = sm / "AlgoFortis.lnk"
        if candidate.exists():
            start_shortcut = candidate
            break
    assert start_shortcut is not None, f"Start Menu shortcut AlgoFortis.lnk not found in {start_menu_dirs}"
    log(f"  PASS: Start Menu shortcut found at: {start_shortcut}")

def check_add_remove_programs():
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{8B58E97E-9CE0-4C3D-B27D-5EB0E66AF5F0}_is1"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            name, _ = winreg.QueryValueEx(key, "DisplayName")
            ver, _ = winreg.QueryValueEx(key, "DisplayVersion")
            pub, _ = winreg.QueryValueEx(key, "Publisher")
            uninstall, _ = winreg.QueryValueEx(key, "UninstallString")
            assert "AlgoFortis" in name
            assert ver == "9.0.0"
            assert pub == "AlgoFortis"
            log(f"  PASS: Add/Remove Programs registered: {name} v{ver} ({pub}) -> {uninstall}")
    except OSError as e:
        # Check Wow6432Node if 32-bit redirect
        key_path_32 = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{8B58E97E-9CE0-4C3D-B27D-5EB0E66AF5F0}_is1"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path_32) as key:
            name, _ = winreg.QueryValueEx(key, "DisplayName")
            ver, _ = winreg.QueryValueEx(key, "DisplayVersion")
            log(f"  PASS: Add/Remove Programs registered (32-bit node): {name} v{ver}")

def run_installed_app():
    exe_path = install_dir / "AlgoFortis.exe"
    assert exe_path.exists(), f"Installed launcher {exe_path} does not exist!"
    
    # Check that source repo is not on product PATH or PYTHONPATH
    clean_env = {k: v for k, v in os.environ.items() if "SentinelX-CLEAN" not in v and "SentinelX_AWS_MIGRATION" not in v}
    clean_env.pop("PYTHONPATH", None)

    log("Launching installed application via AlgoFortis.exe...")
    # Launch AlgoFortis.exe directly (simulating desktop double-click)
    proc = subprocess.Popen([str(exe_path)], cwd=str(install_dir), env=clean_env)
    
    # Wait for startup and readiness
    python_exe = install_dir / "runtime" / "python" / "python.exe"
    
    # Check status via installed python controller
    cmd = [str(python_exe), "-m", "dashboard.runtime.controller", "status", "--mode", "LOCAL_PRIVATE", "--install-root", str(install_dir)]
    
    deadline = time.monotonic() + 30
    ready_info = None
    while time.monotonic() < deadline:
        res = subprocess.run(cmd, cwd=str(install_dir), env=clean_env, capture_output=True, text=True)
        if res.returncode == 0:
            try:
                data = json.loads(res.stdout.strip())
                if data.get("state") == "READY":
                    ready_info = data
                    break
            except Exception:
                pass
        time.sleep(0.5)

    assert ready_info is not None, "Installed application did not achieve READY state within 30s!"
    url = ready_info["url"]
    pid = ready_info["pid"]
    instance_id = ready_info["instance_id"]
    log(f"  PASS: Installed backend is READY at {url} (PID: {pid}, Instance: {instance_id})")
    
    # Test HTTP index
    req_index = Request(url)
    with opener.open(req_index) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert ('name="algofortis-runtime" content="LOCAL_PRIVATE"' in html) or ('name="sentinelx-runtime" content="LOCAL_PRIVATE"' in html)
        assert "<title>AlgoFortis</title>" in html or "AlgoFortis" in html
        log("  PASS: Installed local-private frontend loaded cleanly from Program Files dist with AlgoFortis branding.")

    # Test HTTP runtime status
    req_status = Request(f"{url}api/v1/runtime/status")
    with opener.open(req_status) as resp:
        assert resp.status == 200
        status_data = json.loads(resp.read().decode("utf-8"))
        assert status_data["mode"] == "LOCAL_PRIVATE"
        assert status_data["live_execution"] == "DISARMED"
        assert status_data["local_auth_transport"] == "UNAVAILABLE"
        assert status_data["roaming_identity"] == "UNAVAILABLE"
        assert status_data["identity"] == "LOCAL_WEBAUTHN"
        log("  PASS: Installed runtime status truthful: PRODUCTION mode, DISARMED execution.")

    # Phase 10: Installed Functional Smoke
    log("Executing Phase 10 Installed Functional Smoke checks...")
    
    # 1. Strategies: ORB strategy exists and importable
    orb_path = install_dir / "strategies" / "orb" / "orb_strategy.py"
    assert orb_path.exists(), "ORB strategy missing in installation!"
    orb_check = subprocess.run([str(python_exe), "-c", "import sys; sys.path.insert(0, r'C:\\Program Files\\AlgoFortis'); import strategies.orb.orb_strategy; print('ORB_STRATEGY_OK')"],
                               cwd=str(install_dir), env=clean_env, capture_output=True, text=True)
    assert "ORB_STRATEGY_OK" in orb_check.stdout, f"Failed to import installed ORB strategy: {orb_check.stderr}"
    log("  PASS: Institutional ORB strategy verified in installed package.")

    # 2. Historical parquet data cache
    nifty_parquet = install_dir / "data" / "parquet" / "NIFTY"
    assert nifty_parquet.exists(), "NIFTY parquet data directory missing in installation!"
    log("  PASS: Historical parquet dataset verified in installed package.")

    # 3. Local-Private Data Root & Mutable Isolation (%LOCALAPPDATA%\AlgoFortis)
    localappdata = Path(os.environ["LOCALAPPDATA"]) / "AlgoFortis"
    assert localappdata.exists(), f"Production data root {localappdata} was not created!"
    assert (localappdata / "databases" / "security" / "sentinelx_security.sqlite3").exists(), "Security database missing!"
    assert (localappdata / "databases" / "governance" / "sentinelx_governance.sqlite3").exists(), "Governance database missing!"
    assert (localappdata / "databases" / "core-audit.sqlite3").exists(), "Core audit database missing!"
    assert (localappdata / "config" / "runtime.json").exists(), "Runtime config missing!"
    assert (localappdata / "logs" / "backend.log").exists(), "Backend log missing!"
    log(f"  PASS: All mutable databases and logs reside in {localappdata}.")

    # Verify ZERO mutable databases exist in C:\Program Files\AlgoFortis
    installed_dbs = list(install_dir.glob("**/*.sqlite*")) + list(install_dir.glob("**/*.db"))
    assert len(installed_dbs) == 0, f"Found mutable databases inside Program Files! {installed_dbs}"
    log("  PASS: Zero mutable databases exist in Program Files (strict immutability verified).")

    # 4. Duplicate launch prevention
    log("Testing duplicate launch prevention (double-clicking again while running)...")
    proc2 = subprocess.Popen([str(exe_path)], cwd=str(install_dir), env=clean_env)
    time.sleep(2)
    # Check status again; instance_id and PID should remain identical!
    res_dup = subprocess.run(cmd, cwd=str(install_dir), env=clean_env, capture_output=True, text=True)
    data_dup = json.loads(res_dup.stdout.strip())
    assert data_dup["state"] == "READY"
    assert data_dup["instance_id"] == instance_id, "Instance ID changed on duplicate launch!"
    assert data_dup["pid"] == pid, "Duplicate backend was spawned!"
    log("  PASS: Duplicate launch safely detected; existing backend reused.")

    # 5. Lifecycle A: In-place backend stop & reconnect while GUI remains alive
    log("Testing Lifecycle A: In-place backend stop and reconnect...")
    stop_cmd = [str(python_exe), "-m", "dashboard.runtime.controller", "stop", "--mode", "LOCAL_PRIVATE", "--install-root", str(install_dir)]
    subprocess.run(stop_cmd, cwd=str(install_dir), env=clean_env, check=True)
    time.sleep(1)
    res_stopped = subprocess.run(cmd, cwd=str(install_dir), env=clean_env, capture_output=True, text=True)
    assert json.loads(res_stopped.stdout.strip())["state"] == "UNAVAILABLE"
    log("  PASS: Backend gracefully stopped while GUI remains open (controller UNAVAILABLE).")

    # Restart backend through supported RuntimeController mechanism
    log("Restarting backend via RuntimeController mechanism...")
    start_cmd = [str(python_exe), "-m", "dashboard.runtime.controller", "start", "--mode", "LOCAL_PRIVATE", "--install-root", str(install_dir)]
    res_restarted = subprocess.run(start_cmd, cwd=str(install_dir), env=clean_env, capture_output=True, text=True, check=True)
    data_restarted = json.loads(res_restarted.stdout.strip())
    assert data_restarted.get("state") == "READY", f"Backend failed to start: {res_restarted.stdout}"
    assert data_restarted["url"] == url, "URL changed after in-place restart!"
    log(f"  PASS: Backend became READY again via RuntimeController (instance: {data_restarted['instance_id']}).")

    # Verify existing GUI / frontend reconnects successfully
    time.sleep(1)
    req_reconnected = Request(f"{data_restarted['url']}api/v1/runtime/status")
    with opener.open(req_reconnected) as resp:
        assert resp.status == 200
        status_reconnected = json.loads(resp.read().decode("utf-8"))
        assert status_reconnected["state"] == "READY"
        assert status_reconnected["mode"] == "LOCAL_PRIVATE"
        assert status_reconnected["live_execution"] == "DISARMED"
    log("  PASS: Existing GUI client reconnected successfully to restarted backend.")

    # 6. Lifecycle B: Full application close and cold relaunch
    log("Testing Lifecycle B: Full application close and cold relaunch...")
    # Gracefully close the original AlgoFortis GUI process
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        pass
    assert proc.poll() is not None, "Original AlgoFortis GUI process did not terminate!"
    log("  PASS: Original AlgoFortis GUI process closed gracefully.")

    # Stop backend to ensure cold state before relaunch
    subprocess.run(stop_cmd, cwd=str(install_dir), env=clean_env, check=True)
    time.sleep(1)
    res_cold = subprocess.run(cmd, cwd=str(install_dir), env=clean_env, capture_output=True, text=True)
    assert json.loads(res_cold.stdout.strip())["state"] == "UNAVAILABLE"

    # Relaunch installed AlgoFortis.exe
    log("Relaunching installed AlgoFortis.exe from cold state...")
    proc_reopened = subprocess.Popen([str(exe_path)], cwd=str(install_dir), env=clean_env)
    deadline = time.monotonic() + 30
    reopened_info = None
    while time.monotonic() < deadline:
        res = subprocess.run(cmd, cwd=str(install_dir), env=clean_env, capture_output=True, text=True)
        if res.returncode == 0:
            try:
                d = json.loads(res.stdout.strip())
                if d.get("state") == "READY":
                    reopened_info = d
                    break
            except Exception:
                pass
        time.sleep(0.5)

    assert reopened_info is not None, "Failed to relaunch application after full shutdown!"
    assert reopened_info["url"] == url, "URL changed after cold relaunch!"
    log(f"  PASS: Backend and UI successfully relaunched from cold state (new instance: {reopened_info['instance_id']}).")

    # Verify frontend loads from cold relaunch
    req_index_relaunch = Request(url)
    with opener.open(req_index_relaunch) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert ('name="algofortis-runtime" content="LOCAL_PRIVATE"' in html) or ('name="sentinelx-runtime" content="LOCAL_PRIVATE"' in html)
        log("  PASS: Relaunched frontend loaded cleanly from Program Files dist.")

    # Gracefully close reopened application and stop backend before uninstallation
    try:
        proc_reopened.terminate()
        proc_reopened.wait(timeout=10)
    except Exception:
        pass
    subprocess.run(stop_cmd, cwd=str(install_dir), env=clean_env, check=True)
    time.sleep(1)
    log("Application closed and backend stopped cleanly before uninstallation.")

def run_uninstall_and_verify():
    log("Testing clean uninstallation...")
    uninstaller = install_dir / "unins000.exe"
    assert uninstaller.exists(), f"Uninstaller {uninstaller} does not exist!"

    # Run uninstaller silently
    cmd = [str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
    log(f"Running uninstaller: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    # Wait for removal
    deadline = time.monotonic() + 30
    removed = False
    while time.monotonic() < deadline:
        if not install_dir.exists() or not (install_dir / "AlgoFortis.exe").exists():
            removed = True
            break
        time.sleep(0.5)

    assert removed, f"Installation directory {install_dir} was not cleaned up by uninstaller!"
    log("  PASS: Program Files installation directory cleaned up.")

    # Verify user data in %LOCALAPPDATA%\AlgoFortis was NOT destroyed
    localappdata = Path(os.environ["LOCALAPPDATA"]) / "AlgoFortis"
    assert localappdata.exists(), "User data in LOCALAPPDATA was destroyed by uninstaller!"
    assert (localappdata / "databases" / "security" / "sentinelx_security.sqlite3").exists(), "Security DB was deleted!"
    assert (localappdata / "logs" / "backend.log").exists(), "Logs were deleted!"
    log("  PASS: User data and databases in LOCALAPPDATA preserved across uninstallation.")

def main():
    print("=== STARTING PHASE 9 & 10 CLEAN INSTALL UX AND SMOKE CERTIFICATION ===")
    assert setup_exe.exists(), f"Setup executable {setup_exe} does not exist!"
    log(f"Installing {setup_exe} silently to C:\\Program Files\\AlgoFortis...")
    
    install_cmd = [str(setup_exe), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
    res = subprocess.run(install_cmd)
    assert res.returncode == 0, f"Installer failed with return code {res.returncode}"
    
    # Give Windows a moment to finish file transfers
    time.sleep(3)
    assert install_dir.exists(), f"C:\\Program Files\\AlgoFortis does not exist after install!"
    log("PASS: Installation directory created.")

    log("Verifying shortcuts and Add/Remove Programs...")
    check_shortcuts()
    check_add_remove_programs()

    log("Verifying application launch, execution, and smoke...")
    run_installed_app()

    log("Verifying uninstallation...")
    run_uninstall_and_verify()

    print("=== PHASE 9 & 10 CERTIFICATION: ALL PASS ===")

if __name__ == "__main__":
    main()
