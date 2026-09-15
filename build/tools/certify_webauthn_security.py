"""Certification test suite for AlgoFortis WebAuthn RP/Origin security invariants."""
import sys
from pathlib import Path

clean_root = Path(__file__).resolve().parents[2]
if str(clean_root) not in sys.path:
    sys.path.insert(0, str(clean_root))

from dashboard.backend.security import (
    WebAuthnRelyingParty,
    WebAuthnCeremonyService,
    SecurityError,
    SecurityConfiguration,
)
from dashboard.backend.security_store import SQLiteSecurityStore
from dashboard.runtime.paths import RuntimePaths, RuntimeMode, CurrentUserAcl

def log(msg):
    print(f"[WEBAUTHN CERT] {msg}")

def test_valid_production_profiles():
    log("Test 1: Verifying valid production RP and origin configurations...")
    valid_cases = [
        ("algofortis.com", "https://app.algofortis.com"),
        ("algofortis.com", "https://algofortis.com"),
        ("algofortis.internal", "https://auth.algofortis.internal"),
        ("algofortis-recovery.com", "https://access.algofortis-recovery.com"),
    ]
    for rp_id, origin in valid_cases:
        rp = WebAuthnRelyingParty(rp_id=rp_id, origin=origin, development_only=False)
        rp.validate()
        log(f"  PASS: Valid production profile accepted: {rp_id} -> {origin}")

def test_invalid_production_profiles_fail_closed():
    log("Test 2: Verifying invalid/insecure production profiles FAIL-CLOSED...")
    invalid_cases = [
        # Insecure HTTP scheme in production
        ("algofortis.com", "http://app.algofortis.com", "HTTP scheme rejected in production"),
        # Mismatched arbitrary origin
        ("algofortis.com", "https://attacker.com", "Mismatched domain rejected"),
        # Substring suffix attack (e.g. evilalgofortis.com)
        ("algofortis.com", "https://evilalgofortis.com", "Invalid suffix prefix rejected"),
        # Loopback attempt in production profile
        ("localhost", "https://localhost:8443", "Localhost rejected in production profile"),
        ("127.0.0.1", "https://127.0.0.1:8443", "IP rejected in production profile"),
        # Invalid characters in RP ID
        ("algo fortis.com", "https://algo fortis.com", "Spaces in RP ID rejected"),
        ("algofortis.com/path", "https://algofortis.com", "Path in RP ID rejected"),
        # Missing fields
        ("", "https://app.algofortis.com", "Empty RP ID rejected"),
        ("algofortis.com", "", "Empty origin rejected"),
    ]
    for rp_id, origin, desc in invalid_cases:
        rp = WebAuthnRelyingParty(rp_id=rp_id, origin=origin, development_only=False)
        try:
            rp.validate()
            raise AssertionError(f"FAIL-OPEN: {desc} was accepted for {rp_id} -> {origin}")
        except SecurityError:
            log(f"  PASS: Fail-closed on: {desc} ({rp_id} -> {origin})")

def test_development_profile_isolation():
    log("Test 3: Verifying development profile isolation and constraints...")
    # Valid development profile
    dev_rp = WebAuthnRelyingParty(rp_id="localhost", origin="http://localhost:5173", development_only=True)
    dev_rp.validate()
    log("  PASS: Valid development profile accepted: localhost -> http://localhost:5173")

    # Insecure dev attempts
    invalid_dev = [
        ("algofortis.com", "http://localhost:5173", "Non-localhost RP ID in dev profile"),
        ("localhost", "https://localhost:5173", "HTTPS in dev profile (must be explicit HTTP)"),
        ("localhost", "http://localhost", "Missing port in dev profile"),
        ("localhost", "http://127.0.0.1:5173", "Hostname mismatch in dev profile"),
    ]
    for rp_id, origin, desc in invalid_dev:
        rp = WebAuthnRelyingParty(rp_id=rp_id, origin=origin, development_only=True)
        try:
            rp.validate()
            raise AssertionError(f"FAIL-OPEN: Dev check failed on {desc}")
        except SecurityError:
            log(f"  PASS: Dev fail-closed on: {desc}")

def test_ceremony_service_configuration_and_routing(tmp_path: Path):
    log("Test 4: Verifying WebAuthnCeremonyService profile routing and status...")
    db_path = tmp_path / "test_sec.sqlite3"
    store = SQLiteSecurityStore(db_path, seed_governance=False, profile="test")

    # 1. Configured production service
    normal_rp = WebAuthnRelyingParty(rp_id="algofortis.com", origin="https://app.algofortis.com", development_only=False)
    recovery_rp = WebAuthnRelyingParty(rp_id="algofortis-recovery.com", origin="https://access.algofortis-recovery.com", development_only=False)
    service = WebAuthnCeremonyService(store=store, normal_rp=normal_rp, recovery_rp=recovery_rp)
    
    assert service.configured is True
    assert service.normal_rp_id() == "algofortis.com"
    server, profile = service._server("algofortis.com")
    assert profile.route.value == "NORMAL"
    
    server_rec, profile_rec = service._server("algofortis-recovery.com")
    assert profile_rec.route.value == "BREAK_GLASS"
    log("  PASS: Production ceremony service routes NORMAL and BREAK_GLASS correctly.")

    # 2. Origin verification in FIDO2 server
    assert server._verify("https://app.algofortis.com") is True
    assert server._verify("https://evil.com") is False
    assert server._verify("http://app.algofortis.com") is False
    log("  PASS: FIDO2 server strictly rejects unauthorized origins.")

    # 3. Development service cannot configure as production
    dev_service = WebAuthnCeremonyService(store=store, normal_rp=WebAuthnRelyingParty(rp_id="localhost", origin="http://localhost:5173", development_only=True))
    assert dev_service.normal_rp_id() == "localhost"
    log("  PASS: Development ceremony service operates in isolated localhost profile.")
    
    store.close()

def main():
    print("=== STARTING WEBAUTHN SECURITY AND RP/ORIGIN CERTIFICATION ===")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        test_valid_production_profiles()
        test_invalid_production_profiles_fail_closed()
        test_development_profile_isolation()
        test_ceremony_service_configuration_and_routing(Path(td))
    print("=== WEBAUTHN SECURITY CERTIFICATION: ALL PASS ===")

if __name__ == "__main__":
    main()
