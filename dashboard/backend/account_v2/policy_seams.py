"""Track-P policy seams consumed by S2 without implementing updater/telemetry backends."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .contracts import EntitlementTimeEvidence


class PolicyViolation(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class UpdateSafeWindowPolicy:
    policy_id: str
    version: str
    allowed_engine_states: tuple[str, ...]
    allow_open_positions: bool
    session_calendar_ref: str
    applicability: str


@dataclass(frozen=True, slots=True)
class UpdateSafeWindowDecision:
    allowed: bool
    reason: str


def evaluate_update_safe_window(
    policy: UpdateSafeWindowPolicy | None,
    *,
    engine_state: str,
    has_open_positions: bool,
) -> UpdateSafeWindowDecision:
    if policy is None:
        return UpdateSafeWindowDecision(False, "UPDATE_POLICY_UNAVAILABLE")
    if engine_state not in policy.allowed_engine_states:
        return UpdateSafeWindowDecision(False, "ENGINE_STATE_NOT_ALLOWED")
    if has_open_positions and not policy.allow_open_positions:
        return UpdateSafeWindowDecision(False, "OPEN_POSITIONS_BLOCK_UPDATE")
    return UpdateSafeWindowDecision(True, "UPDATE_SAFE_WINDOW_ALLOWED")


@dataclass(frozen=True, slots=True)
class EntitlementTimeDecision:
    status: str
    entitlement_dependent_new_operation_allowed: bool
    protective_safety_allowed: bool = True


def evaluate_entitlement_time(
    evidence: EntitlementTimeEvidence,
    *,
    observed_wall_time: datetime,
) -> EntitlementTimeDecision:
    if (
        evidence.monotonic_anchor is None
        or evidence.monotonic_elapsed_seconds is None
        or not evidence.boot_session_id
    ):
        return EntitlementTimeDecision("ENTITLEMENT_TIME_UNCERTAIN", False)
    if evidence.monotonic_elapsed_seconds < 0:
        return EntitlementTimeDecision("ENTITLEMENT_TIME_UNCERTAIN", False)
    if observed_wall_time < evidence.last_successful_server_check_in:
        return EntitlementTimeDecision("ENTITLEMENT_TIME_UNCERTAIN", False)
    if evidence.server_issued_at > evidence.last_successful_server_check_in:
        return EntitlementTimeDecision("ENTITLEMENT_TIME_UNCERTAIN", False)

    trusted_now = evidence.last_successful_server_check_in + timedelta(
        seconds=evidence.monotonic_elapsed_seconds
    )
    if trusted_now > evidence.lease_expires_at:
        return EntitlementTimeDecision("ENTITLEMENT_EXPIRED", False)
    return EntitlementTimeDecision("ENTITLEMENT_TIME_VALID", True)


_FORBIDDEN_TELEMETRY_DATA_CLASSES = frozenset(
    {
        "strategy_content",
        "broker_credentials",
        "broker_tokens",
        "raw_trade_logs",
        "balances",
        "unrestricted_trading_data",
    }
)


@dataclass(frozen=True, slots=True)
class TelemetryPrivacyPolicy:
    policy_id: str
    version: str
    opt_in: bool
    allowed_data_classes: frozenset[str]

    def __post_init__(self) -> None:
        forbidden = self.allowed_data_classes & _FORBIDDEN_TELEMETRY_DATA_CLASSES
        if forbidden:
            raise PolicyViolation(
                "forbidden telemetry data classes: " + ",".join(sorted(forbidden))
            )


@dataclass(frozen=True, slots=True)
class ProductionIdentityMigration:
    publisher: str
    production_domain: str
    production_rp_id: str
    requires_fresh_production_webauthn: bool = True
    requires_device_reproof: bool = True

    def can_promote_existing_webauthn(self, *, source_environment: str) -> bool:
        # Credentials scoped to dev/staging RP IDs/origins never become production
        # credentials through metadata changes. Production requires fresh ceremony.
        return False
