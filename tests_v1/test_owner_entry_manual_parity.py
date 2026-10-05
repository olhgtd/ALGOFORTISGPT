from pathlib import Path


def test_owner_setup_keeps_donor_recovery_code_checkpoint():
    source = Path("dashboard/web/src/visual-lab/secure-entry/LocalOwnerSetupCard.tsx").read_text(encoding="utf-8")
    assert "recovery_codes" in source
    assert 'id="recovery-codes-card"' in source
    assert 'id="recovery-codes-grid"' in source
    assert 'id="confirm-recovery-saved-btn"' in source
    assert "SAVE YOUR RECOVERY CODES" in source
    assert "I HAVE SAVED THESE CODES" in source


def test_owner_backend_restores_persistent_single_use_recovery_authority():
    store = Path("dashboard/backend/security_store.py").read_text(encoding="utf-8")
    router = Path("dashboard/backend/account_v2/password_router.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS recovery_codes" in store
    assert "def create_recovery_codes" in store
    assert "def verify_recovery_code" in store
    assert "def recover_password_with_code" in store
    assert '"recovery_codes"' in router
    assert '"/api/v1/auth/local/recovery/verify"' in router
    assert '"/api/v1/auth/local/recovery/reset"' in router


def test_owner_locked_package_uses_legacy_manual_entry_shell():
    main = Path("dashboard/web/src/main.tsx").read_text(encoding="utf-8")
    legacy = Path("dashboard/web/src/visual-lab/secure-entry/LegacyUserSecureEntryApp.tsx").read_text(encoding="utf-8")
    assert 'lockedWorkspace === "user" || lockedWorkspace === "owner"' in main
    assert 'appTarget={lockedWorkspace}' in main
    assert "ownerBootstrapStatus" in legacy
    assert "onSwitchToLogin" in legacy
    assert "LegacyLocalRecoveryCard" in legacy
