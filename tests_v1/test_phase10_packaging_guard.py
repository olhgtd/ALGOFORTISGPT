"""Phase 10 packaging and production-release boundary tests."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISS = ROOT / "build" / "tools" / "algofortis_installer.iss"
BUILD = ROOT / "build" / "tools" / "build_installer.ps1"


def test_installer_requires_injected_release_metadata_instead_of_guessed_production_identity() -> None:
    source = ISS.read_text(encoding="utf-8")

    assert '#ifndef MyAppPublisher' in source
    assert '#ifndef MyAppURL' in source
    assert '#ifndef ReleaseEnvironment' in source
    assert '#define MyAppPublisher "AlgoFortis"' not in source
    assert '#define MyAppURL "https://app.algofortis.com"' not in source


def test_build_script_has_explicit_qualification_vs_production_modes() -> None:
    source = BUILD.read_text(encoding="utf-8")

    assert '[ValidateSet("QUALIFICATION", "PRODUCTION")]' in source
    assert '$ReleaseEnvironment = "QUALIFICATION"' in source
    assert "PENDING_EXTERNAL" in source
    assert "production release requires finalized publisher" in source.lower()
    assert "production release requires finalized canonical url" in source.lower()


def test_production_packaging_requires_authenticode_and_timestamp_authority() -> None:
    source = BUILD.read_text(encoding="utf-8")

    assert "SIGNTOOL_CERT_PATH" in source
    assert "SIGNTOOL_TIMESTAMP_URL" in source
    assert "production release requires authenticode" in source.lower()
    assert "Get-AuthenticodeSignature" in source
    assert "TimeStamperCertificate" in source


def test_qualification_build_is_explicitly_nonproduction_and_never_auto_arms_live() -> None:
    build_source = BUILD.read_text(encoding="utf-8")
    iss_source = ISS.read_text(encoding="utf-8")

    assert "QUALIFICATION BUILD" in build_source
    assert "READ_ONLY/DISARMED" in build_source
    combined = (build_source + "\n" + iss_source).upper()
    assert "AUTO_ARM" not in combined
    assert "ALLOW_LIVE" not in combined
