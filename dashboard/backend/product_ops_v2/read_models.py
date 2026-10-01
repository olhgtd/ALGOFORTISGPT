from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProductOpsHealth:
    unresolved_incidents: int
    alert_health: str
    privacy_requests: tuple[tuple[str, int], ...]
    stale_policy_count: int
    backup_status: str
    restore_status: str
    rollback_status: str
    active_policy_versions: tuple[str, ...]
    runbook_status: str | None = None

    def __post_init__(self):
        if self.unresolved_incidents < 0 or self.stale_policy_count < 0:
            raise ValueError("health counts must be non-negative")
        if any(count < 0 for _, count in self.privacy_requests):
            raise ValueError("privacy request counts must be non-negative")


@dataclass(frozen=True, slots=True)
class UserPrivacyReadModel:
    notice_policy_ref: str
    notice_fingerprint: str
    consent_state: str
    request_statuses: tuple[tuple[str, str], ...]
    identity_authority: str | None = None
    device_session_state: str | None = None

    def __post_init__(self):
        if self.notice_fingerprint and len(self.notice_fingerprint) != 64:
            raise ValueError("notice fingerprint must be SHA-256 length")


def build_health(
    *,
    incidents: int,
    alert_health: str,
    request_counts: dict[str, int],
    stale_policy_count: int,
    backup_status: str,
    restore_status: str,
    rollback_status: str,
    active_policy_versions: tuple[str, ...],
    runbook_status: str | None = None,
) -> ProductOpsHealth:
    if incidents < 0 or stale_policy_count < 0 or any(count < 0 for count in request_counts.values()):
        raise ValueError("health counts must be non-negative")
    return ProductOpsHealth(
        incidents,
        alert_health,
        tuple(sorted(request_counts.items())),
        stale_policy_count,
        backup_status,
        restore_status,
        rollback_status,
        tuple(sorted(active_policy_versions)),
        runbook_status,
    )
