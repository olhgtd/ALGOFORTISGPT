"""Real Windows install/launch/uninstall smoke for split AlgoFortis Owner/User packages."""
from __future__ import annotations
import hashlib, json, os, subprocess, time
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[2]
BRAND_ROOT = ROOT / "assets" / "branding" / "AlgoFortis"
OWNER_BRAND = BRAND_ROOT / "AlgoFortis_Owner_Logo.png"
USER_BRAND = BRAND_ROOT / "AlgoFortis_User_Logo.png"
LOCAL_DATA = Path(os.environ["LOCALAPPDATA"]) / "AlgoFortis"
OPENER = build_opener(ProxyHandler({}))
PACKAGES = (
    ("OWNER", ROOT / "build" / "installer" / "AlgoFortis-Owner-Setup.exe",
     Path(r"C:\Program Files\AlgoFortis\Owner"), "AlgoFortisOwner.exe", OWNER_BRAND),
    ("USER", ROOT / "build" / "installer" / "AlgoFortis-User-Setup.exe",
     Path(r"C:\Program Files\AlgoFortis\User"), "AlgoFortisUser.exe", USER_BRAND),
)

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def status(install: Path) -> dict:
    py=install/"runtime"/"python"/"python.exe"
    r=subprocess.run([str(py),"-m","dashboard.runtime.controller","status","--mode","LOCAL_PRIVATE","--install-root",str(install)],
                     cwd=str(install),capture_output=True,text=True,check=True)
    return json.loads(r.stdout.strip())

def wait_state(install: Path, expected: str, timeout=35):
    deadline=time.monotonic()+timeout
    last={}
    while time.monotonic()<deadline:
        try:
            last=status(install)
            if last.get("state")==expected: return last
        except Exception:
            pass
        time.sleep(.5)
    raise AssertionError(f"{install}: expected {expected}, last={last}")

def close_window(proc):
    ps=f"$p=Get-Process -Id {proc.pid} -ErrorAction Stop; if(-not $p.CloseMainWindow()){{exit 2}}"
    r=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-Command",ps],capture_output=True,text=True)
    assert r.returncode==0,(r.stdout,r.stderr)
    proc.wait(timeout=35)

def uninstall(install: Path):
    items=sorted(install.glob("unins*.exe"))
    assert items,f"uninstaller missing: {install}"
    subprocess.run([str(items[0]),"/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART"],check=True)

def main():
    print("=== ALGOFORTIS OWNER/USER REAL INSTALL CERT ===")
    for role,setup,install,exe_name,brand_source in PACKAGES:
        brand_hash=sha(brand_source)
        assert setup.exists(),setup
        r=subprocess.run([str(setup),"/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/MERGETASKS=desktopicon"])
        assert r.returncode==0,(role,r.returncode)
        exe=install/exe_name
        assert exe.exists(),exe
        assert not (install/"AlgoFortis.exe").exists(),"generic launcher leaked into role installer"
        other_exe="AlgoFortisUser.exe" if role=="OWNER" else "AlgoFortisOwner.exe"
        assert not (install/other_exe).exists(),"opposite role launcher leaked"
        assert sha(install/"algofortis_logo.png")==brand_hash,f"{role} installed root logo does not match final role brand"
        assert sha(install/"dashboard"/"web"/"dist"/"algofortis_logo.png")==brand_hash,f"{role} web logo does not match final role brand"
        assert sha(install/"dashboard"/"web"/"dist"/"favicon.png")==brand_hash,f"{role} favicon does not match final role brand"
        assert (install/"algofortis.ico").exists()
        assert (install/"dashboard"/"web"/"dist"/"index.html").exists()
        assert (install/"runtime"/"python"/"python.exe").exists()

        proc=subprocess.Popen([str(exe)],cwd=str(install))
        ready=wait_state(install,"READY")
        runtime_url=ready["url"]
        with OPENER.open(Request(runtime_url.rstrip("/") + "/api/v1/runtime/status")) as response:
            runtime_status=json.loads(response.read().decode("utf-8"))
        assert runtime_status["mode"]=="LOCAL_PRIVATE"
        assert runtime_status["live_execution"]=="DISARMED"
        close_window(proc)
        wait_state(install,"UNAVAILABLE")
        uninstall(install)
        assert LOCAL_DATA.exists(),"LOCALAPPDATA user data was deleted"
        print(f"PASS: {role} install/launch/close/uninstall")

    print("LIVE_STATE=READ_ONLY/DISARMED")
    print("OWNER_USER_INSTALL_CERT=PASS")

if __name__=="__main__":
    main()
