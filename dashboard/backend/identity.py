"""Identity provider boundary. Installation identity is never user authority."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from .domain import (UserIdentity, Role, Lifecycle, AccountAccessStatus, ActivationStatus,
                     ServiceEntitlementStatus)
from .security import SecurityError
from dashboard.runtime.paths import atomic_json
import json


class IdentityProvider(Protocol):
    configured: bool
    def verify(self, assertion: dict) -> UserIdentity: ...


class UnavailableRoamingIdentity:
    """No remote enrollment, email/OTP, or portable subject authority is deployed."""
    configured = False

    def verify(self, assertion: dict) -> UserIdentity:
        raise SecurityError("Cross-PC identity authority is not configured")


def persisted_identity(row) -> UserIdentity:
    """Strict reconstruction from the security store, never request claims."""
    if row is None:
        raise SecurityError("Identity unavailable")
    return UserIdentity(
        UUID(row["user_id"]), Role(row["role"]), Lifecycle(row["lifecycle"]), row["display_name"],
        sx_id=row["sx_id"], account_status=AccountAccessStatus(row["account_status"]),
        activation_status=ActivationStatus(row["activation_status"]),
        service_status=ServiceEntitlementStatus(row["service_status"]),
        service_started_at=datetime.fromisoformat(row["service_started_at"]) if row["service_started_at"] else None,
        service_expires_at=datetime.fromisoformat(row["service_expires_at"]) if row["service_expires_at"] else None,
        service_term_type=row["service_term_type"], custom_term_value=row["custom_term_value"],
        custom_term_unit=row["custom_term_unit"],
    )


def local_owner(store, config_path) -> UserIdentity:
    """Restore the durable Owner; reserve a bootstrap subject without seeding a user."""
    owners = [row for row in store.list_users() if row["role"] == "OWNER"]
    if len(owners) > 1:
        raise SecurityError("Ambiguous local Owner authority")
    if owners:
        row = owners[0]
        return UserIdentity(
            UUID(row["user_id"]), Role.OWNER, Lifecycle(row["lifecycle"]), row["display_name"],
            sx_id=row["sx_id"], account_status=AccountAccessStatus(row["account_status"]),
            activation_status=ActivationStatus(row["activation_status"]),
            service_status=ServiceEntitlementStatus(row["service_status"]),
            service_started_at=datetime.fromisoformat(row["service_started_at"]) if row["service_started_at"] else None,
            service_expires_at=datetime.fromisoformat(row["service_expires_at"]) if row["service_expires_at"] else None,
            service_term_type=row["service_term_type"], custom_term_value=row["custom_term_value"],
        )
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        subject = UUID(config["bootstrap_subject"])
    else:
        subject = uuid4()
        atomic_json(config_path, {"version": 1, "bootstrap_subject": str(subject)})
    return UserIdentity(subject, Role.OWNER, Lifecycle.ACTIVE, "Owner")
