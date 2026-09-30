"""Deferred security-boundary tests for the canonical AlgoFortis entry gate."""
from __future__ import annotations

from pathlib import Path

from build.tools.check_owner_admin_boundary import check_source_text
from dashboard.backend.account_v2.password_router import (
    PasswordActivationRequest,
    PasswordLoginRequest,
)
from pydantic import ValidationError
import pytest


ENTRY_FILES = (
    "dashboard/backend/account_v2/password_accounts.py",
    "dashboard/backend/account_v2/password_router.py",
    "dashboard/web/src/visual-lab/secure-entry/SecureEntryApp.tsx",
    "dashboard/web/src/visual-lab/secure-entry/FirstTimeCustomerFlow.tsx",
    "dashboard/web/src/visual-lab/secure-entry/ReturningUserFlow.tsx",
)


def test_entry_guard_rejects_broker_mutation_and_risk_bypass_tokens() -> None:
    source = """
from engine.broker_adapters.angel_adapter import AngelAdapter

def authenticate():
    place_order()
    _mint_approved_order()
"""
    failures = check_source_text("dashboard/backend/account_v2/password_router.py", source)
    assert any("forbidden module" in item for item in failures)
    assert any("forbidden authority token 'place_order'" in item for item in failures)
    assert any("forbidden authority token '_mint_approved_order'" in item for item in failures)


def test_canonical_entry_sources_have_no_broker_mutation_or_sample_authority() -> None:
    for relative in ENTRY_FILES:
        source = Path(relative).read_text(encoding="utf-8")
        assert check_source_text(relative, source) == []


def test_login_request_cannot_supply_role_or_workspace() -> None:
    with pytest.raises(ValidationError):
        PasswordLoginRequest.model_validate({
            "identifier": "owner@example.com",
            "password": "Password123!",
            "role": "OWNER",
        })
    with pytest.raises(ValidationError):
        PasswordLoginRequest.model_validate({
            "identifier": "user@example.com",
            "password": "Password123!",
            "workspace": "owner",
        })


def test_activation_request_cannot_supply_role_or_account_state() -> None:
    base = {
        "identifier": "AF-U-ABCD-2345",
        "activation_code": "AF-ACT-AAAA-BBBB-CCCC",
        "email": "user@example.com",
        "password": "Password123!",
        "confirm_password": "Password123!",
    }
    with pytest.raises(ValidationError):
        PasswordActivationRequest.model_validate({**base, "role": "OWNER"})
    with pytest.raises(ValidationError):
        PasswordActivationRequest.model_validate({**base, "account_status": "ACTIVE"})


def test_password_router_does_not_log_or_return_password_material() -> None:
    source = Path("dashboard/backend/account_v2/password_router.py").read_text(encoding="utf-8")
    forbidden_response_tokens = (
        '"password_hash"',
        '"password_salt"',
        'payload={"password"',
        'payload={"activation_code"',
    )
    for token in forbidden_response_tokens:
        assert token not in source


def test_secure_entry_has_no_direct_dashboard_authority_or_broker_calls() -> None:
    source = Path("dashboard/web/src/visual-lab/secure-entry/SecureEntryApp.tsx").read_text(encoding="utf-8")
    assert "place_order" not in source
    assert "cancel_order" not in source
    assert "_mint_approved_order" not in source
    assert "engine.broker_adapters" not in source
