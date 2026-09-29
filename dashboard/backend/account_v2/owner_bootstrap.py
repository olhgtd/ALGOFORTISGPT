"""Fail-closed Owner singleton/bootstrap policy for V2 anywhere-login.

A fresh local installation MUST NOT infer that the global Owner does not exist
just because its local security database is empty. Owner creation is a global
account-authority decision. Local emptiness is therefore UNKNOWN, not ABSENT.

This module intentionally does not implement the central account service. It
provides the runtime policy seam that prevents duplicate Owner provisioning
until that server-authoritative service is connected.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OwnerPresence(str, Enum):
    LOCAL_EXISTS = "LOCAL_EXISTS"
    REMOTE_EXISTS = "REMOTE_EXISTS"
    ABSENT_CONFIRMED = "ABSENT_CONFIRMED"
    UNKNOWN = "UNKNOWN"


class OwnerEntryFlow(str, Enum):
    LOCAL_LOGIN = "LOCAL_LOGIN"
    RETURNING_USER = "RETURNING_USER"
    LOCAL_OWNER_SETUP = "LOCAL_OWNER_SETUP"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class OwnerBootstrapDecision:
    presence: OwnerPresence
    setup_allowed: bool
    flow: OwnerEntryFlow
    authority: str
    reason: str

    def public_dict(self) -> dict[str, object]:
        return {
            "owner_presence": self.presence.value,
            "owner_setup_allowed": self.setup_allowed,
            "recommended_flow": self.flow.value,
            "authority": self.authority,
            "reason": self.reason,
        }


def resolve_owner_bootstrap(
    *,
    local_owner_initialized: bool,
    roaming_identity_configured: bool,
    explicit_trusted_local_bootstrap: bool = False,
    production: bool = True,
) -> OwnerBootstrapDecision:
    """Resolve entry behavior without ever treating local emptiness as global absence.

    Production never permits local Owner creation without a future explicit
    server-authoritative ABSENT_CONFIRMED decision. For development/local-private
    bootstrap, an operator may opt in explicitly; this is never inferred from an
    empty database.
    """
    if local_owner_initialized:
        return OwnerBootstrapDecision(
            presence=OwnerPresence.LOCAL_EXISTS,
            setup_allowed=False,
            flow=OwnerEntryFlow.LOCAL_LOGIN,
            authority="LOCAL_DURABLE_OWNER",
            reason="existing durable Owner found on this installation",
        )

    if roaming_identity_configured:
        return OwnerBootstrapDecision(
            presence=OwnerPresence.UNKNOWN,
            setup_allowed=False,
            flow=OwnerEntryFlow.RETURNING_USER,
            authority="CENTRAL_ACCOUNT_AUTHORITY",
            reason="fresh installation must authenticate against central account authority",
        )

    if explicit_trusted_local_bootstrap and not production:
        return OwnerBootstrapDecision(
            presence=OwnerPresence.ABSENT_CONFIRMED,
            setup_allowed=True,
            flow=OwnerEntryFlow.LOCAL_OWNER_SETUP,
            authority="EXPLICIT_LOCAL_BOOTSTRAP",
            reason="operator explicitly enabled one-time non-production Owner bootstrap",
        )

    return OwnerBootstrapDecision(
        presence=OwnerPresence.UNKNOWN,
        setup_allowed=False,
        flow=OwnerEntryFlow.UNAVAILABLE,
        authority="FAIL_CLOSED",
        reason="local database is empty but global Owner presence is not authoritatively known",
    )
