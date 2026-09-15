"""Phase 9 domain values with no engine authority duplicated here."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from math import isfinite
from typing import Mapping
from uuid import UUID


class ActivationStatus(str, Enum):
    DRAFT = "DRAFT"
    INVITED = "INVITED"
    REDEEMED = "REDEEMED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class AccountAccessStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class ServiceEntitlementStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"


class ServiceTermType(str, Enum):
    ONE_MONTH = "1_MONTH"
    THREE_MONTHS = "3_MONTHS"
    SIX_MONTHS = "6_MONTHS"
    TWELVE_MONTHS = "12_MONTHS"
    LIFETIME = "LIFETIME"
    CUSTOM_DAYS = "CUSTOM_DAYS"
    CUSTOM_MONTHS = "CUSTOM_MONTHS"


def add_calendar_months(dt: datetime, months: int) -> datetime:
    """Exact calendar-month arithmetic with month-end day clamping (OD-AUTH-24)."""
    orig_year = dt.year
    orig_month = dt.month
    orig_day = dt.day

    total_months = orig_month - 1 + months
    target_year = orig_year + total_months // 12
    target_month = total_months % 12 + 1

    if target_month in {1, 3, 5, 7, 8, 10, 12}:
        max_days = 31
    elif target_month in {4, 6, 9, 11}:
        max_days = 30
    else:
        is_leap = (target_year % 4 == 0 and target_year % 100 != 0) or (target_year % 400 == 0)
        max_days = 29 if is_leap else 28

    clamped_day = min(orig_day, max_days)
    return dt.replace(year=target_year, month=target_month, day=clamped_day)


def compute_service_expiry(
    start_dt: datetime,
    term_type: ServiceTermType | str,
    custom_value: int | None = None,
    custom_unit: str | None = None,
) -> datetime | None:
    """Derive service expiration timestamp following exact frozen V1 semantics (OD-AUTH-19, OD-AUTH-24)."""
    term_str = term_type.value if isinstance(term_type, ServiceTermType) else str(term_type)
    if term_str == "LIFETIME":
        return None
    if term_str == "1_MONTH":
        return add_calendar_months(start_dt, 1)
    if term_str == "3_MONTHS":
        return add_calendar_months(start_dt, 3)
    if term_str == "6_MONTHS":
        return add_calendar_months(start_dt, 6)
    if term_str == "12_MONTHS":
        return add_calendar_months(start_dt, 12)
    if term_str in {"CUSTOM_DAYS", "CUSTOM"} and (custom_unit == "DAYS" or term_str == "CUSTOM_DAYS"):
        days = custom_value or 30
        return start_dt + timedelta(days=days)
    if term_str in {"CUSTOM_MONTHS", "CUSTOM"} and (custom_unit == "MONTHS" or term_str == "CUSTOM_MONTHS"):
        months = custom_value or 1
        return add_calendar_months(start_dt, months)
    return add_calendar_months(start_dt, 3)


class Role(str, Enum):
    OWNER = "OWNER"
    USER = "USER"


class Lifecycle(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"


class TrustState(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class AccessRoute(str, Enum):
    NORMAL = "NORMAL"
    BREAK_GLASS = "BREAK_GLASS"


class SessionRisk(str, Enum):
    NORMAL = "NORMAL"
    STEP_UP_REQUIRED = "STEP_UP_REQUIRED"
    DENY_OR_REVIEW = "DENY_OR_REVIEW"


class StrategyStage(str, Enum):
    ADDED = "ADDED"
    VALIDATED = "VALIDATED"
    BACKTEST_ELIGIBLE = "BACKTEST_ELIGIBLE"
    PAPER_ELIGIBLE = "PAPER_ELIGIBLE"
    LIVE_ELIGIBLE = "LIVE_ELIGIBLE"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True)
class UserIdentity:
    """Immutable user identity; never use a display name for tenancy."""
    user_id: UUID
    role: Role
    lifecycle: Lifecycle = Lifecycle.ACTIVE
    display_name: str = "Owner"
    sx_id: str | None = None
    account_status: AccountAccessStatus = AccountAccessStatus.ACTIVE
    activation_status: ActivationStatus = ActivationStatus.REDEEMED
    service_status: ServiceEntitlementStatus = ServiceEntitlementStatus.ACTIVE
    service_started_at: datetime | None = None
    service_expires_at: datetime | None = None
    service_term_type: str | None = "LIFETIME"
    custom_term_value: int | None = None
    custom_term_unit: str | None = None

    @property
    def namespace(self) -> str:
        return f"users/usr_{self.user_id}"

    def effective_service_status(self, now_utc: datetime | None = None) -> ServiceEntitlementStatus:
        """Dynamic evaluation under server-authoritative UTC wall-clock (OD-AUTH-20, OD-AUTH-24)."""
        if self.role is Role.OWNER:
            return ServiceEntitlementStatus.ACTIVE
        if self.activation_status in {ActivationStatus.DRAFT, ActivationStatus.INVITED} or self.service_started_at is None:
            return ServiceEntitlementStatus.NOT_STARTED
        if self.service_term_type == "LIFETIME" and self.service_expires_at is None:
            return ServiceEntitlementStatus.ACTIVE
        if self.service_expires_at is not None:
            now = now_utc or datetime.now(timezone.utc)
            if now >= self.service_expires_at:
                return ServiceEntitlementStatus.EXPIRED
            return ServiceEntitlementStatus.ACTIVE
        return self.service_status

    def is_workspace_eligible(self, workspace: str, now_utc: datetime | None = None) -> bool:
        """Authoritative workspace eligibility decision (AUTH_ACCESS_CONTRACT_V1.md §4.3)."""
        if self.lifecycle != Lifecycle.ACTIVE or self.account_status != AccountAccessStatus.ACTIVE:
            return False
        if workspace == "owner":
            return self.role is Role.OWNER
        if workspace == "user":
            if self.role is Role.OWNER:
                return True
            return self.effective_service_status(now_utc) == ServiceEntitlementStatus.ACTIVE
        return False


@dataclass(frozen=True)
class TrustedValue:
    value: object | None
    trust: TrustState
    as_of_utc: datetime | None
    source_identity: str | None = None
    state_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if self.trust is TrustState.FRESH and self.as_of_utc is None:
            raise ValueError("FRESH values require an authoritative as-of timestamp")
        if self.as_of_utc is not None and self.as_of_utc.tzinfo is None:
            raise ValueError("as_of_utc must be timezone-aware")

    def public_dict(self) -> dict[str, object | None]:
        return {
            "value": self.value,
            "trust": self.trust.value,
            "as_of_utc": self.as_of_utc.isoformat() if self.as_of_utc else None,
            "source_identity": self.source_identity,
            "state_fingerprint": self.state_fingerprint,
        }


@dataclass(frozen=True)
class StrategyQualityEvidence:
    oos_walk_forward: float
    robustness_stability: float
    drawdown_quality: float
    expectancy: float
    profit_factor: float
    statistical_confidence: float
    trade_evidence_sufficiency: float


@dataclass(frozen=True)
class StrategyQualityScore:
    score: float
    grade: str
    components: Mapping[str, float]


class StrategyQualityScorer:
    """Evidence score only. It deliberately has no promotion side effects."""
    _WEIGHTS = {
        "oos_walk_forward": 25.0,
        "robustness_stability": 20.0,
        "drawdown_quality": 15.0,
        "expectancy": 15.0,
        "profit_factor": 10.0,
        "statistical_confidence": 10.0,
        "trade_evidence_sufficiency": 5.0,
    }

    @classmethod
    def calculate(cls, evidence: StrategyQualityEvidence) -> StrategyQualityScore:
        normalized = {}
        for name, weight in cls._WEIGHTS.items():
            raw = float(getattr(evidence, name))
            if not isfinite(raw) or not 0.0 <= raw <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
            normalized[name] = raw * weight
        score = round(sum(normalized.values()), 2)
        grade = (
            "Exceptional" if score >= 90 else "Strong" if score >= 80 else
            "Good" if score >= 70 else "Moderate" if score >= 60 else
            "Weak / Needs Review"
        )
        return StrategyQualityScore(score=score, grade=grade, components=normalized)


class StrategyQualityAuthority:
    """Read-only adapter over existing backtest/validation evidence."""
    def __init__(self, evidence_reader: callable | None = None) -> None:
        self._evidence_reader = evidence_reader

    def score_for(self, strategy_version_identity: str) -> StrategyQualityScore | None:
        if not isinstance(strategy_version_identity, str) or not strategy_version_identity.strip() or not callable(self._evidence_reader):
            return None
        try:
            evidence = self._evidence_reader(strategy_version_identity)
        except Exception:
            return None
        if not isinstance(evidence, StrategyQualityEvidence):
            return None
        return StrategyQualityScorer.calculate(evidence)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ── Slice 4: Owner Strategy, Connection & Dataset Governance Authorities ──

class StrategyAdminStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DEPRECATED = "DEPRECATED"


class SystemReadinessStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class OwnerAllowanceStatus(str, Enum):
    ALLOWED = "ALLOWED"
    HOLD = "HOLD"


class EffectiveEligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    BLOCKED = "BLOCKED"


def compute_strategy_effective_eligibility(
    system_readiness: str,
    owner_allowance: str,
    is_suspended: bool,
) -> tuple[str, str]:
    """Derive effective sandbox eligibility enforcing fail-closed non-bypassable rules."""
    if is_suspended:
        return "BLOCKED", "Global strategy suspension is active (Owner administrative hold)."
    if system_readiness != "READY":
        return "BLOCKED", "System readiness gate unsatisfied. Owner allowance cannot override engine/validation prerequisites."
    if owner_allowance != "ALLOWED":
        return "BLOCKED", "Placed on administrative hold by Owner."
    return "ELIGIBLE", "System readiness verified and Owner allowance granted."


class ConnectionHealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"


class ConnectionAuthStatus(str, Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    CONFIGURED = "CONFIGURED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    EXPIRED = "EXPIRED"


class ConnectionOwnerAllowance(str, Enum):
    ALLOWED = "ALLOWED"
    HOLD = "HOLD"


class CapabilityEffectiveStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    BLOCKED = "BLOCKED"


def compute_capability_effective(
    conn_health: str,
    conn_allowance: str,
    cap_system_status: str,
    cap_auth_status: str,
    cap_owner_allowance: str,
    blocker_reason: str | None = None,
) -> tuple[str, str | None]:
    """Derive effective capability status enforcing connector hold and offline boundaries."""
    if conn_allowance != "ALLOWED":
        return "BLOCKED", "Connection placed on administrative hold by Owner."
    if conn_health == "OFFLINE":
        return "BLOCKED", "Connection transport adapter is offline."
    if cap_owner_allowance != "ALLOWED":
        return "BLOCKED", "Capability placed on administrative hold by Owner."
    if cap_system_status in {"UNSUPPORTED", "OFFLINE"}:
        return "BLOCKED", blocker_reason or f"Capability is {cap_system_status.lower()} by provider adapter."
    if cap_auth_status != "AUTHORIZED":
        reason_tag = "EXPIRED" if cap_auth_status == "EXPIRED" else ("AUTH REQUIRED" if cap_auth_status == "BLOCKED_AUTH" else "NOT CONFIGURED")
        return "BLOCKED", blocker_reason or f"Capability requires valid authentication ({reason_tag.lower()})."
    return "AVAILABLE", None


class DatasetSystemReadiness(str, Enum):
    SYSTEM_READY = "SYSTEM_READY"
    BLOCKED = "BLOCKED"


class DatasetOwnerApproval(str, Enum):
    APPROVED = "APPROVED"
    HOLD = "HOLD"
    REJECTED = "REJECTED"


class DatasetEffectiveReadiness(str, Enum):
    READY_FOR_BACKTEST = "READY_FOR_BACKTEST"
    BLOCKED = "BLOCKED"


EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def compute_dataset_effective_readiness(
    system_readiness: str,
    owner_approval: str,
    system_blocker: str | None = None,
    provenance: str | None = None,
    hash_sha256: str | None = None,
) -> tuple[str, str | None]:
    """Derive effective dataset readiness. Owner approval cannot override calendar gaps, unready data, or vacuous hashes."""
    clean_hash = (hash_sha256 or "").removeprefix("sha256:").lower()
    if clean_hash == EMPTY_SHA256:
        return "BLOCKED", "Dataset has empty-string SHA-256 digest and cannot be certified for execution."
    if system_readiness != "SYSTEM_READY":
        return "BLOCKED", system_blocker or "Dataset failed schema validation or trading calendar gap verification."
    if owner_approval != "APPROVED":
        return "BLOCKED", "Owner placed dataset on administrative hold." if owner_approval == "HOLD" else "Owner rejected dataset."
    return "READY_FOR_BACKTEST", None
