"""Phase 8 Installed Application Security Certification for AlgoFortis using live server."""
import json
import os
import shutil
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen, build_opener, ProxyHandler
from urllib.error import HTTPError

clean_root = Path(__file__).resolve().parents[2]
if str(clean_root) not in sys.path:
    sys.path.insert(0, str(clean_root))

from dashboard.runtime.paths import RuntimePaths, RuntimeMode
from dashboard.runtime.controller import RuntimeController

def log(msg):
    print(f"[PHASE 8 SECURITY] {msg}")

def test_live_security_invariants():
    # Place isolated appdata outside tempdir so SensitiveStorage won't reject it as temporary
    test_appdata_root = clean_root / "build" / "test_p8_localappdata"
    if test_appdata_root.exists():
        shutil.rmtree(test_appdata_root, ignore_errors=True)
    appdata = test_appdata_root / "Local"
    appdata.mkdir(parents=True, exist_ok=True)

    orig_local = os.environ.get("LOCALAPPDATA")
    os.environ["LOCALAPPDATA"] = str(appdata)

    try:
        install_root = clean_root / "build" / "stage"
        paths = RuntimePaths.resolve(RuntimeMode.PRODUCTION, install_root=install_root)
        controller = RuntimeController(paths, timeout=25)

        log("Starting live production server via RuntimeController...")
        info = controller.start()
        assert info["state"] == "READY"
        url = info["url"]
        log(f"Live server ready at {url}")

        opener = build_opener(ProxyHandler({}))

        # Test 1: Frontend index.html served at root with mode marker and NO secret leakage
        log("Test 1: Frontend index.html served with runtime mode marker...")
        req = Request(url)
        with opener.open(req) as resp:
            assert resp.status == 200
            html = resp.read().decode("utf-8")
            assert ('name="algofortis-runtime" content="PRODUCTION"' in html) or ('name="algofortis-runtime" content="PRODUCTION"' in html)
            assert "control_secret" not in html
        log("  PASS: Frontend index served cleanly with runtime marker and zero leaked secrets.")

        # Test 2: Same-Origin Host header enforcement
        log("Test 2: Same-Origin Host header enforcement...")
        req_bad_host = Request(f"{url}api/v1/runtime/status", headers={"Host": "attacker.com"})
        try:
            opener.open(req_bad_host)
            assert False, "Should have failed with 403 on foreign Host"
        except HTTPError as e:
            assert e.code == 403, f"Expected 403, got {e.code}"
        log("  PASS: Foreign Host header rejected with 403.")

        # Test 3: Same-Origin Origin header enforcement
        log("Test 3: Same-Origin Origin header enforcement...")
        req_bad_orig = Request(f"{url}api/v1/runtime/status", headers={"Origin": "https://evil.attacker.com"})
        try:
            opener.open(req_bad_orig)
            assert False, "Should have failed with 403 on foreign Origin"
        except HTTPError as e:
            assert e.code == 403, f"Expected 403, got {e.code}"
        log("  PASS: Foreign Origin header rejected with 403.")

        # Test 4: Production WebAuthn fail-closed
        log("Test 4: Production WebAuthn fail-closed on unapproved transport...")
        req_webauthn = Request(f"{url}api/v1/auth/webauthn/authentication/options",
                               data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        try:
            opener.open(req_webauthn)
            assert False, "Should have failed with 503 on unapproved HTTP transport"
        except HTTPError as e:
            assert e.code == 503, f"Expected 503, got {e.code}"
        log("  PASS: WebAuthn requires approved HTTPS transport (503).")

        # Test 5: Production runtime status
        log("Test 5: Production runtime status truthfulness...")
        req_status = Request(f"{url}api/v1/runtime/status")
        with opener.open(req_status) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["mode"] == "PRODUCTION"
            assert data["local_auth_transport"] == "UNAVAILABLE"
            assert data["roaming_identity"] == "UNAVAILABLE"
            assert data["live_execution"] == "DISARMED"
            assert data["identity"] == "LOCAL_WEBAUTHN"
        log("  PASS: Truthful runtime status verified.")

        # Test 6: Control secret endpoint protection
        log("Test 6: Runtime control endpoint unauthorized access rejected...")
        req_ctrl = Request(f"{url}api/v1/runtime/control/status")
        try:
            opener.open(req_ctrl)
            assert False, "Should have failed with 403 without control secret"
        except HTTPError as e:
            assert e.code == 403, f"Expected 403, got {e.code}"
        log("  PASS: Runtime control endpoint rejected without valid control secret (403).")

        # Test 7: Device authorization boundary
        log("Test 7: Unauthenticated device endpoint rejected...")
        req_dev = Request(f"{url}api/v1/security/devices")
        try:
            opener.open(req_dev)
            assert False, "Should have failed with 401 unauthenticated"
        except HTTPError as e:
            assert e.code == 401, f"Expected 401, got {e.code}"
        log("  PASS: /api/v1/security/devices rejected with 401.")

        log("Stopping live server...")
        controller.stop()
        assert controller.status()["state"] == "UNAVAILABLE"
        log("Server stopped successfully.")

    finally:
        if orig_local:
            os.environ["LOCALAPPDATA"] = orig_local
        else:
            os.environ.pop("LOCALAPPDATA", None)
        if test_appdata_root.exists():
            shutil.rmtree(test_appdata_root, ignore_errors=True)

if __name__ == "__main__":
    print("=== STARTING PHASE 8 INSTALLED APP SECURITY CERTIFICATION ===")
    test_live_security_invariants()
    print("=== PHASE 8 INSTALLED APP SECURITY CERTIFICATION: ALL PASS ===")
