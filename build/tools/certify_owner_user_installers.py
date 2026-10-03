"""Real Windows install/launch/uninstall smoke for split AlgoFortis Owner/User packages."""
from __future__ import annotations
import hashlib, json, os, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRAND = ROOT / "assets" / "branding" / "AlgoFortis" / "AlgoFortis_Logo_Master.png"
LOCAL_DATA = Path(os.environ["LOCALAPPDATA"]) / "AlgoFortis"
PACKAGES = (
    ("OWNER", ROOT / "build" / "installer" / "AlgoFortis-Owner-Setup.exe",
     Path(r"C:\Program Files\AlgoFortis\Owner"), "AlgoFortisOwner.exe", "AlgoFortis User.lnk"),
    ("USER", ROOT / "build" / "installer" / "AlgoFortis-User-Setup.exe",
     Path(r"C:\Program Files\AlgoFortis\User"), "AlgoFortisUser.exe", "AlgoFortis Owner.lnk"),
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
    brand_hash=sha(BRAND)
    for role,setup,install,exe_name,other_shortcut in PACKAGES:
        assert setup.exists(),setup
        r=subprocess.run([str(setup),"/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/MERGETASKS=desktopicon"])
        assert r.returncode==0,(role,r.returncode)
        exe=install/exe_name
        assert exe.exists(),exe
        assert not (install/"AlgoFortis.exe").exists(),"generic launcher leaked into role installer"
        other_exe="AlgoFortisUser.exe" if role=="OWNER" else "AlgoFortisOwner.exe"
        assert not (install/other_exe).exists(),"opposite role launcher leaked"
        assert sha(install/"algofortis_logo.png")==brand_hash,"installed logo is not approved fortress master"
        assert (install/"algofortis.ico").exists()
        assert (install/"dashboard"/"web"/"dist"/"index.html").exists()
        assert (install/"runtime"/"python"/"python.exe").exists()

        proc=subprocess.Popen([str(exe)],cwd=str(install))
        ready=wait_state(install,"READY")
        assert ready["mode"]=="LOCAL_PRIVATE"
        close_window(proc)
        wait_state(install,"UNAVAILABLE")
        uninstall(install)
        assert LOCAL_DATA.exists(),"LOCALAPPDATA user data was deleted"
        print(f"PASS: {role} install/launch/close/uninstall")

    print("LIVE_STATE=READ_ONLY/DISARMED")
    print("OWNER_USER_INSTALL_CERT=PASS")

if __name__=="__main__":
    main()
