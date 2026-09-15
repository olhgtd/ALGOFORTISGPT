"""Phase 5 Slice 4A — Option subscription management.

Coordinates logical multi-strategy quote subscriptions over shared physical
provider subscriptions.

Key contracts:
- Multi-owner reference sets (InstrumentIdentity -> set[SubscriptionOwnerKey])
- Logical 0 -> 1 transition returns need_subscribe=True
- Logical 1 -> 0 transition returns need_unsubscribe=True
- Same-owner acquire/release idempotency
- Deterministic logical contract switching
- Reconnect subscription snapshot retention
"""

from __future__ import annotations

from typing import Iterable

from engine.data.feeds.live_feed import SubscriptionOwnerKey
from engine.portfolio.model import InstrumentIdentity

__all__ = [
    "OptionSubscriptionManager",
    "deterministic_subscription_order",
]


def deterministic_subscription_order(
    subscriptions: Iterable[InstrumentIdentity],
) -> tuple[InstrumentIdentity, ...]:
    """Deterministically sort instrument identities by canonical fields.

    Guarantees reproducible sequential ordering for reconnect / replay
    without relying on dict insertion order or network arrival order.
    """
    for item in subscriptions:
        if not isinstance(item, InstrumentIdentity):
            raise TypeError("all items must be InstrumentIdentity instances")
    return tuple(
        sorted(
            subscriptions,
            key=lambda ident: (
                ident.market,
                ident.instrument,
                ident.segment,
                repr(ident.underlying),
                ident.expiry.isoformat() if ident.expiry is not None else "",
                str(ident.strike) if ident.strike is not None else "",
                ident.option_type or "",
            ),
        )
    )


class OptionSubscriptionManager:
    """Deterministic, provider-independent option subscription coordinator."""

    def __init__(self) -> None:
        self._subscriptions: dict[InstrumentIdentity, set[SubscriptionOwnerKey]] = {}

    def acquire(self, owner: SubscriptionOwnerKey, identity: InstrumentIdentity) -> bool:
        """Acquire subscription for owner.

        Returns True ONLY for logical 0 -> 1 transition, indicating physical
        provider subscription is required.
        """
        if not isinstance(owner, SubscriptionOwnerKey):
            raise TypeError("owner must be a SubscriptionOwnerKey")
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")

        if identity not in self._subscriptions:
            self._subscriptions[identity] = {owner}
            return True

        self._subscriptions[identity].add(owner)
        return False

    def release(self, owner: SubscriptionOwnerKey, identity: InstrumentIdentity) -> bool:
        """Release subscription for owner.

        Returns True ONLY for logical 1 -> 0 transition, indicating physical
        provider unsubscription is required.
        """
        if not isinstance(owner, SubscriptionOwnerKey):
            raise TypeError("owner must be a SubscriptionOwnerKey")
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")

        owners = self._subscriptions.get(identity)
        if not owners or owner not in owners:
            return False

        owners.remove(owner)
        if not owners:
            del self._subscriptions[identity]
            return True
        return False

    def switch(
        self,
        owner: SubscriptionOwnerKey,
        old_identity: InstrumentIdentity,
        new_identity: InstrumentIdentity,
    ) -> tuple[bool, bool]:
        """Perform deterministic logical contract switch for owner.

        Validates all arguments prior to any mutation. If old_identity == new_identity,
        performs zero mutations and returns (False, False).

        Returns:
            (need_unsubscribe_old, need_subscribe_new)
        """
        if not isinstance(owner, SubscriptionOwnerKey):
            raise TypeError("owner must be a SubscriptionOwnerKey")
        if not isinstance(old_identity, InstrumentIdentity):
            raise TypeError("old_identity must be an InstrumentIdentity")
        if not isinstance(new_identity, InstrumentIdentity):
            raise TypeError("new_identity must be an InstrumentIdentity")

        if old_identity == new_identity:
            return (False, False)

        need_unsub = self.release(owner, old_identity)
        need_sub = self.acquire(owner, new_identity)
        return (need_unsub, need_sub)

    def is_subscribed(self, identity: InstrumentIdentity) -> bool:
        """Return whether the instrument currently has at least one active owner."""
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        return identity in self._subscriptions and len(self._subscriptions[identity]) > 0

    def owners_for(self, identity: InstrumentIdentity) -> frozenset[SubscriptionOwnerKey]:
        """Return immutable set of active owners for an instrument."""
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        return frozenset(self._subscriptions.get(identity, ()))

    def active_subscriptions(self) -> frozenset[InstrumentIdentity]:
        """Return immutable set of all currently subscribed instruments."""
        return frozenset(self._subscriptions.keys())
