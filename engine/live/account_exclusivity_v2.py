"""Local fail-closed exclusivity for one Live owner per broker account."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from engine.persistence.live_account_exclusivity_store_v2 import (
    LiveAccountExclusivityStoreConflict,
    LiveAccountExclusivityStoreV2,
)


class LiveAccountExclusivityConflict(RuntimeError):
    pass


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


@dataclass(frozen=True, slots=True)
class LiveAccountOwner:
    broker_id: str
    broker_account_ref: str
    device_id: str
    session_family_id: str
    ownership_nonce: str
    acquired_at_utc: datetime

    def __post_init__(self) -> None:
        for field in (
            "broker_id",
            "broker_account_ref",
            "device_id",
            "session_family_id",
            "ownership_nonce",
        ):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        object.__setattr__(self, "acquired_at_utc", _aware(self.acquired_at_utc, "acquired_at_utc"))


class LiveAccountExclusivityV2:
    """Local broker-account ownership backstop; never arms Live by itself."""

    def __init__(self, store: LiveAccountExclusivityStoreV2) -> None:
        if not isinstance(store, LiveAccountExclusivityStoreV2):
            raise TypeError("store must be LiveAccountExclusivityStoreV2")
        self._store = store

    def acquire(self, candidate: LiveAccountOwner) -> LiveAccountOwner:
        if not isinstance(candidate, LiveAccountOwner):
            raise TypeError("candidate must be LiveAccountOwner")
        try:
            return self._store.save(candidate)
        except LiveAccountExclusivityStoreConflict as exc:
            raise LiveAccountExclusivityConflict(str(exc)) from exc

    def verify(self, candidate: LiveAccountOwner) -> bool:
        if not isinstance(candidate, LiveAccountOwner):
            raise TypeError("candidate must be LiveAccountOwner")
        current = self._store.load(candidate.broker_id, candidate.broker_account_ref)
        return current == candidate

    def release(self, candidate: LiveAccountOwner) -> None:
        if not isinstance(candidate, LiveAccountOwner):
            raise TypeError("candidate must be LiveAccountOwner")
        current = self._store.load(candidate.broker_id, candidate.broker_account_ref)
        if current is None:
            raise LiveAccountExclusivityConflict("broker account has no active local owner")
        if current != candidate or current.ownership_nonce != candidate.ownership_nonce:
            raise LiveAccountExclusivityConflict("broker account ownership proof does not match")
        if not self._store.clear(
            candidate.broker_id,
            candidate.broker_account_ref,
            candidate.ownership_nonce,
        ):
            raise LiveAccountExclusivityConflict("broker account owner changed before release")

    def restore_after_restart(self, *, broker_id: str, broker_account_ref: str) -> None:
        """Drop persisted ownership; restart never re-arms ownership from disk."""
        current = self._store.load(broker_id, broker_account_ref)
        if current is None:
            return
        if not self._store.clear(current.broker_id, current.broker_account_ref, current.ownership_nonce):
            raise LiveAccountExclusivityConflict("unable to clear stale restart ownership")


__all__ = [
    "LiveAccountExclusivityConflict",
    "LiveAccountExclusivityV2",
    "LiveAccountOwner",
]
