"""AI/Laya capability authorization layered strictly above S2 identity authority."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from .contracts import (
    DeviceSessionGateResult,
    DeviceSessionGateStatus,
    IntelligenceCapability,
    IntelligenceEntitlementDecision,
)


class IntelligenceEntitlementStore(Protocol):
    def list_for_user(self, user_id: UUID) -> tuple[IntelligenceCapability, ...]: ...
    def replace_for_user(self, user_id: UUID, capabilities: tuple[IntelligenceCapability, ...]) -> None: ...


class SQLiteIntelligenceEntitlementStore:
    """Capability rows stored inside the existing durable security authority."""

    def __init__(self, security_store) -> None:
        if security_store is None or not hasattr(security_store, "_transaction") or not hasattr(security_store, "_conn"):
            raise RuntimeError("S2 security authority unavailable")
        self._store = security_store
        with self._store._transaction() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS ai_user_entitlements (
                    user_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY(user_id, capability)
                )"""
            )

    def list_for_user(self, user_id: UUID) -> tuple[IntelligenceCapability, ...]:
        if not isinstance(user_id, UUID):
            raise TypeError("user_id must be UUID")
        rows = self._store._conn.execute(
            "SELECT capability FROM ai_user_entitlements WHERE user_id = ? AND enabled = 1 ORDER BY capability",
            (str(user_id),),
        ).fetchall()
        try:
            return tuple(IntelligenceCapability(str(row["capability"])) for row in rows)
        except Exception as exc:
            raise RuntimeError("invalid intelligence entitlement authority row") from exc

    def replace_for_user(self, user_id: UUID, capabilities: tuple[IntelligenceCapability, ...]) -> None:
        if not isinstance(user_id, UUID):
            raise TypeError("user_id must be UUID")
        if not isinstance(capabilities, tuple) or any(not isinstance(item, IntelligenceCapability) for item in capabilities):
            raise TypeError("capabilities must be tuple[IntelligenceCapability, ...]")
        values = tuple(sorted(set(capabilities), key=lambda item: item.value))
        now = datetime.now(timezone.utc).isoformat()
        with self._store._transaction() as cur:
            cur.execute("DELETE FROM ai_user_entitlements WHERE user_id = ?", (str(user_id),))
            for capability in values:
                cur.execute(
                    "INSERT INTO ai_user_entitlements(user_id, capability, enabled, updated_at_utc) VALUES (?, ?, 1, ?)",
                    (str(user_id), capability.value, now),
                )


class IntelligenceEntitlementService:
    """Capability authorization; S2 remains the identity/device/session gate."""

    def __init__(self, store: IntelligenceEntitlementStore) -> None:
        if not callable(getattr(store, "list_for_user", None)) or not callable(getattr(store, "replace_for_user", None)):
            raise TypeError("store must provide list_for_user/replace_for_user")
        self._store = store

    def list_for_user(self, user_id: UUID) -> tuple[IntelligenceCapability, ...]:
        return self._store.list_for_user(user_id)

    def set_for_user(
        self,
        user_id: UUID,
        capabilities: tuple[IntelligenceCapability, ...],
        *,
        actor_is_owner: bool,
    ) -> tuple[IntelligenceCapability, ...]:
        if actor_is_owner is not True:
            raise PermissionError("Owner authority required to change intelligence entitlements")
        self._store.replace_for_user(user_id, capabilities)
        return self._store.list_for_user(user_id)

    def authorize(
        self,
        gate: DeviceSessionGateResult,
        capability: IntelligenceCapability,
    ) -> IntelligenceEntitlementDecision:
        if not isinstance(gate, DeviceSessionGateResult):
            raise TypeError("gate must be DeviceSessionGateResult")
        if not isinstance(capability, IntelligenceCapability):
            raise TypeError("capability must be IntelligenceCapability")
        if gate.status is not DeviceSessionGateStatus.VALID:
            return IntelligenceEntitlementDecision(
                gate.user_id,
                capability,
                False,
                f"S2_{gate.status.value}",
                gate.status,
                gate.authority_evidence_ref,
            )
        try:
            allowed = capability in self._store.list_for_user(gate.user_id)
        except Exception:
            return IntelligenceEntitlementDecision(
                gate.user_id,
                capability,
                False,
                "ENTITLEMENT_AUTHORITY_UNAVAILABLE",
                gate.status,
                gate.authority_evidence_ref,
            )
        return IntelligenceEntitlementDecision(
            gate.user_id,
            capability,
            allowed,
            "GRANTED" if allowed else "CAPABILITY_NOT_GRANTED",
            gate.status,
            gate.authority_evidence_ref,
        )


__all__ = [
    "IntelligenceEntitlementService",
    "IntelligenceEntitlementStore",
    "SQLiteIntelligenceEntitlementStore",
]
