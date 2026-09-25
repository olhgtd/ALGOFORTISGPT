from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from engine.paper.contracts_v2 import PaperPositionRecord
from engine.paper.protective_integrity_v2 import (
    ProtectiveIntegrityChecker,
    ProtectiveIntegrityVerdict,
)
from engine.paper.session_v2 import SessionValidityEvaluator

NOW = datetime(2026, 9, 25, 10, 30, tzinfo=timezone.utc)
EXPIRY = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)


def _position() -> PaperPositionRecord:
    return PaperPositionRecord(
        position_id="position-1",
        instrument="NIFTY26SEP25000CE",
        quantity=Decimal("50"),
        average_price=Decimal("100"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("5"),
        protective_policy_ref="protective/orb-v1",
        protective_state="VALID",
        expiry_metadata="2026-09-25T10:00:00+00:00",
        session_metadata="2026-09-25",
    )


def test_clean_state_cannot_override_invalid_protective_integrity():
    result = ProtectiveIntegrityChecker().check(
        _position(),
        policy_ref="protective/orb-v1",
        observed_state="MISSING",
    )
    assert result.verdict is ProtectiveIntegrityVerdict.INVALID
    assert result.entry_eligible is False
    assert result.action == "HALT_ENTRIES"


def test_missing_protective_policy_is_uncertain_and_fail_closed():
    result = ProtectiveIntegrityChecker().check(
        _position(),
        policy_ref=None,
        observed_state="VALID",
    )
    assert result.verdict is ProtectiveIntegrityVerdict.UNCERTAIN
    assert result.entry_eligible is False


def test_open_option_at_expiry_without_policy_halts_without_inventing_flatten():
    result = SessionValidityEvaluator().evaluate(
        instrument="NIFTY26SEP25000CE",
        expiry_at=EXPIRY,
        now=NOW,
        has_open_position=True,
        request_new_entry=False,
        expiry_policy_ref=None,
    )
    assert result.allowed is False
    assert result.action == "HALT_ENTRIES"
    assert result.auto_flatten is False
    assert result.reason == "MISSING_EXPIRY_POLICY"


def test_expired_contract_never_accepts_fresh_entry_even_with_policy_ref():
    result = SessionValidityEvaluator().evaluate(
        instrument="NIFTY26SEP25000CE",
        expiry_at=EXPIRY,
        now=NOW,
        has_open_position=False,
        request_new_entry=True,
        expiry_policy_ref="expiry/nse-options-v1",
    )
    assert result.allowed is False
    assert result.action == "HALT_ENTRIES"
    assert result.auto_flatten is False
    assert result.reason == "EXPIRED_CONTRACT_NEW_ENTRY"


def test_expiry_policy_reference_only_authorizes_policy_dispatch_not_auto_flatten():
    result = SessionValidityEvaluator().evaluate(
        instrument="NIFTY26SEP25000CE",
        expiry_at=EXPIRY,
        now=NOW,
        has_open_position=True,
        request_new_entry=False,
        expiry_policy_ref="expiry/nse-options-v1",
    )
    assert result.allowed is True
    assert result.action == "APPLY_VERSIONED_EXPIRY_POLICY"
    assert result.auto_flatten is False
