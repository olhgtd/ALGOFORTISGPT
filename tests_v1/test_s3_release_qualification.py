import base64
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from dashboard.backend.signature_verification import Ed25519KeyringVerifier

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def decision_section(register: str, od: str) -> str:
    return register.split(f"**{od} ", 1)[1].split("\n**OD-V2-", 1)[0]


def test_s3_release_build_is_fail_closed_for_required_signing():
    build = read("build/tools/build_installer.ps1")
    assert "RequireSignature" in build
    assert "Get-AuthenticodeSignature" in build
    assert "launcherSigned" in build
    assert "installerSigned" in build
    assert "SIGNED RELEASE cannot continue" in build
    assert "NOT RELEASE-QUALIFIED" in build
    assert "C:\\Users\\Ragini Music" not in build


def test_phase10_status_does_not_false_claim_g10_or_live_authority():
    status = read("docs/v2/phase10/PHASE10_RELEASE_QUALIFICATION_STATUS.md")
    assert "G10: BLOCKED" in status
    assert "READ_ONLY / DISARMED" in status
    assert "It must not emit G10=PASS" in status
    assert "real-money Live authorization" in status


def test_phase10_preserves_owner_decision_boundaries():
    register = read("ALGOFORTIS_V2_OWNER_DECISIONS.md")
    for od in ("OD-V2-20", "OD-V2-21", "OD-V2-22", "OD-V2-23"):
        assert "*Status:* **FROZEN**" in decision_section(register, od)
    for od in ("OD-V2-18", "OD-V2-26"):
        assert "*Status:* OPEN" in decision_section(register, od)


def test_phase10_workflow_qualifies_s3_without_claiming_g10():
    workflow = read(".github/workflows/v2-phase10-release-qualification.yml")
    for marker in (
        "windows-latest",
        "windows-2022",
        "check_s3_release_qualification.py",
        "s3_release_probe.py",
        "python -m pytest tests_v1 -q",
        "check_phase9_product_ops.py",
        "check_live_reunion_boundary.py",
        "check_riskgate_fast_path_boundary.py",
        "check_owner_admin_boundary.py",
        "S3_CROSS_WINDOWS_COMPARE=PASS",
        "G10_RELEASE_GATE=BLOCKED",
    ):
        assert marker in workflow
    assert "G10=PASS" not in workflow


def test_ed25519_keyring_verifier_accepts_only_trusted_key_and_payload():
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
    public_key = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    verifier = Ed25519KeyringVerifier({"release-ed25519-v1": public_key})
    payload = b"algofortis-s3-signed-artifact"
    signature = base64.b64encode(private_key.sign(payload)).decode("ascii")

    assert verifier(payload, signature, "release-ed25519-v1")
    assert not verifier(payload + b"-tampered", signature, "release-ed25519-v1")
    assert not verifier(payload, signature, "unknown-key")
    assert not verifier(payload, "not-base64***", "release-ed25519-v1")
