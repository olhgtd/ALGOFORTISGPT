"""Policy-bound long-term memory domain for Phase 8 research/intelligence agents."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from engine.ai.v2.contracts import DataClass


class MemoryPolicyError(ValueError):
    pass


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MemoryPolicyError(f"{name} must be a non-empty string")
    return value.strip()


def _aware(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise MemoryPolicyError(f"{name} must be timezone-aware datetime")
    return value


_ALLOWED_DATA_CLASSES = {
    DataClass.MARKET_RESEARCH,
    DataClass.DATASET_DERIVED,
    DataClass.NEWS_RESEARCH,
    DataClass.STRATEGY_RESEARCH,
}


@dataclass(frozen=True, slots=True)
class MemoryItem:
    user_id: str
    item_id: str
    value: str | None
    provenance_ref: str
    data_class: DataClass
    policy_ref: str
    created_at: datetime
    updated_at: datetime
    version: int
    active: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "user_id", _text(self.user_id, "user_id"))
        object.__setattr__(self, "item_id", _text(self.item_id, "item_id"))
        if self.active:
            object.__setattr__(self, "value", _text(self.value, "value"))
        elif self.value is not None:
            raise MemoryPolicyError("inactive memory tombstone must not retain payload")
        object.__setattr__(self, "provenance_ref", _text(self.provenance_ref, "provenance_ref"))
        if self.data_class not in _ALLOWED_DATA_CLASSES:
            raise MemoryPolicyError("data_class is not allowed for long-term memory")
        object.__setattr__(self, "policy_ref", _text(self.policy_ref, "policy_ref"))
        created = _aware(self.created_at, "created_at")
        updated = _aware(self.updated_at, "updated_at")
        if updated < created:
            raise MemoryPolicyError("updated_at cannot precede created_at")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise MemoryPolicyError("version must be a positive integer")


@dataclass(frozen=True, slots=True)
class MemoryAuditEvent:
    action: str
    user_id: str
    item_id: str
    version: int
    provenance_ref: str
    data_class: str
    policy_ref: str
    occurred_at: datetime


class MemoryRepository(Protocol):
    def get(self, user_id: str, item_id: str) -> MemoryItem | None: ...
    def put(self, item: MemoryItem) -> None: ...


class InMemoryMemoryRepository:
    """Test/reference repository; production persistence is injected elsewhere."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], MemoryItem] = {}

    def get(self, user_id: str, item_id: str) -> MemoryItem | None:
        return self._items.get((user_id, item_id))

    def put(self, item: MemoryItem) -> None:
        self._items[(item.user_id, item.item_id)] = item


class MemoryService:
    def __init__(self, repository: MemoryRepository, audit_sink) -> None:
        if not callable(getattr(repository, "get", None)) or not callable(getattr(repository, "put", None)):
            raise MemoryPolicyError("repository must implement get/put")
        if not callable(audit_sink):
            raise MemoryPolicyError("audit_sink must be callable")
        self._repo = repository
        self._audit = audit_sink

    @staticmethod
    def _validate_class(data_class: object) -> DataClass:
        if not isinstance(data_class, DataClass) or data_class not in _ALLOWED_DATA_CLASSES:
            raise MemoryPolicyError("data_class is not allowed for long-term memory")
        return data_class

    def _audit_before_put(self, action: str, item: MemoryItem, occurred_at: datetime) -> None:
        event = MemoryAuditEvent(
            action=action,
            user_id=item.user_id,
            item_id=item.item_id,
            version=item.version,
            provenance_ref=item.provenance_ref,
            data_class=item.data_class.value,
            policy_ref=item.policy_ref,
            occurred_at=occurred_at,
        )
        try:
            self._audit(event)
        except Exception as exc:
            raise MemoryPolicyError("memory audit failed") from exc
        self._repo.put(item)

    def store(self, *, user_id: str, item_id: str, value: str, provenance_ref: str, data_class: DataClass, policy_ref: str, now: datetime) -> MemoryItem:
        user_id = _text(user_id, "user_id")
        item_id = _text(item_id, "item_id")
        provenance_ref = _text(provenance_ref, "provenance_ref")
        policy_ref = _text(policy_ref, "policy_ref")
        now = _aware(now, "now")
        data_class = self._validate_class(data_class)
        existing = self._repo.get(user_id, item_id)
        if existing is not None and existing.active:
            raise MemoryPolicyError("active memory item already exists; use correct")
        item = MemoryItem(
            user_id=user_id, item_id=item_id, value=value, provenance_ref=provenance_ref,
            data_class=data_class, policy_ref=policy_ref, created_at=now, updated_at=now,
            version=1 if existing is None else existing.version + 1, active=True,
        )
        self._audit_before_put("STORE", item, now)
        return item

    def store_provider_output(self, **kwargs) -> MemoryItem:
        return self.store(**kwargs)

    def get(self, user_id: str, item_id: str) -> MemoryItem | None:
        user_id = _text(user_id, "user_id")
        item_id = _text(item_id, "item_id")
        item = self._repo.get(user_id, item_id)
        return item if item is not None and item.active else None

    def correct(self, *, user_id: str, item_id: str, value: str, provenance_ref: str, now: datetime) -> MemoryItem:
        user_id = _text(user_id, "user_id")
        item_id = _text(item_id, "item_id")
        provenance_ref = _text(provenance_ref, "provenance_ref")
        now = _aware(now, "now")
        current = self._repo.get(user_id, item_id)
        if current is None or not current.active:
            raise MemoryPolicyError("active memory item not found")
        item = MemoryItem(
            user_id=user_id, item_id=item_id, value=value, provenance_ref=provenance_ref,
            data_class=current.data_class, policy_ref=current.policy_ref, created_at=current.created_at,
            updated_at=now, version=current.version + 1, active=True,
        )
        self._audit_before_put("CORRECT", item, now)
        return item

    def delete(self, *, user_id: str, item_id: str, now: datetime) -> None:
        user_id = _text(user_id, "user_id")
        item_id = _text(item_id, "item_id")
        now = _aware(now, "now")
        current = self._repo.get(user_id, item_id)
        if current is None or not current.active:
            raise MemoryPolicyError("active memory item not found")
        tombstone = MemoryItem(
            user_id=user_id, item_id=item_id, value=None, provenance_ref=current.provenance_ref,
            data_class=current.data_class, policy_ref=current.policy_ref, created_at=current.created_at,
            updated_at=now, version=current.version + 1, active=False,
        )
        self._audit_before_put("DELETE", tombstone, now)


__all__ = [
    "MemoryPolicyError", "MemoryItem", "MemoryAuditEvent", "MemoryRepository",
    "InMemoryMemoryRepository", "MemoryService",
]
