"""S2 wrapper around the existing durable WebAuthn ceremony authority."""
from __future__ import annotations

from typing import Any

from dashboard.backend.security import WebAuthnCeremonyService, WebAuthnRelyingParty

from .contracts import ProductionIdentityPolicy


class ProductionCredentialReenrollmentRequired(PermissionError):
    """A non-production credential cannot be promoted into production trust."""


def validate_relying_party_profile(*, rp_id: str, origin: str, development_only: bool) -> WebAuthnRelyingParty:
    profile = WebAuthnRelyingParty(rp_id=rp_id, origin=origin, development_only=development_only)
    profile.validate()
    return profile


class WebAuthnAuthority:
    def __init__(self, ceremonies: WebAuthnCeremonyService) -> None:
        self._ceremonies = ceremonies

    @staticmethod
    def require_credential_compatible(*, source: ProductionIdentityPolicy, target: ProductionIdentityPolicy) -> None:
        if target.environment.lower() != "production":
            return
        same_identity = (
            source.environment.lower() == "production"
            and source.rp_id == target.rp_id
            and source.origin == target.origin
            and not target.production_migration_required
        )
        if not same_identity:
            raise ProductionCredentialReenrollmentRequired(
                "fresh production WebAuthn enrollment and device re-proof are required"
            )

    def issue_authentication(self, **kwargs: Any) -> dict[str, object]:
        return self._ceremonies.issue_authentication(**kwargs)

    def complete_authentication(self, **kwargs: Any) -> tuple[str, str]:
        return self._ceremonies.complete_authentication(**kwargs)
