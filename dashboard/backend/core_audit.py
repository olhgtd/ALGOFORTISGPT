"""Phase 9 authoritative audit coordinator and transactional outbox protocol.

Governed by AlgoFortis Owner Decisions (ADR §131):
1. Transactional outbox + staged mutation + idempotent core-audit intent/outcome protocol.
2. Core Audit remains the ONLY authoritative audit truth.
3. engine SCHEMA_VERSION remains exactly 7.
4. Security/Governance stores use independent schema migration (V1 -> V2) for outbox/recovery metadata.
5. Deterministic operation_id through canonical_domain_identity and append-once event identity.
6. Core Audit lifecycle event types under AuditEventFamily.PHASE9_MUTATION (D16-E22):
   - PHASE9_MUTATION_INTENT
   - PHASE9_MUTATION_APPLIED
   - PHASE9_MUTATION_REJECTED
   - PHASE9_MUTATION_FAILED
7. OUTCOME_PENDING is subordinate-store recovery state only, NOT a Core Audit event type.
8. SESSION_STARTED is NOT reused for unrelated Phase 9 mutations.
9. Plaintext bearer tokens and secrets are strictly redacted before serialization into audit metadata.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Mapping, Protocol, Sequence
from uuid import UUID, uuid4

from engine.audit.model import (
    AuditEvent,
    AuditEventFamily,
    AuditEventType,
    AuditIntegrityError,
    canonical_json_dumps,
    derive_audit_event_id,
    recorded_at_utc_now,
)
from .domain import utc_now


class OutboxStageState(str, Enum):
    """Subordinate-store outbox lifecycle states."""

    STAGED = "STAGED"
    INTENT_RECORDED = "INTENT_RECORDED"
    COMMITTED_PENDING_AUDIT = "COMMITTED_PENDING_AUDIT"  # OUTCOME_PENDING subordinate state
    VERIFIED_APPLIED = "VERIFIED_APPLIED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class CoreAuditAppendAuthority(Protocol):
    """Protocol matching Core SQLitePaperStateStore audit append capability."""

    def append_audit_events(self, events: Sequence[AuditEvent]) -> tuple[AuditEvent, ...]: ...


class CoreAuditQueryAuthority(Protocol):
    """Protocol for querying core audit events."""

    def get_audit_event_by_id(self, event_id: str) -> AuditEvent | None: ...


def _redact_sensitive_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Strictly redacts plaintext secrets, passwords, and bearer tokens from audit payloads."""
    if not payload:
        return {}
    safe: dict[str, Any] = {}
    for key, value in payload.items():
        lower_key = key.lower()
        if lower_key in {"token", "bootstrap_token", "access_token", "bearer", "password", "secret", "raw_token"}:
            if isinstance(value, str) and value:
                safe[f"{key}_hash"] = hashlib.sha256(value.encode("utf-8")).hexdigest()
            else:
                safe[key] = "[REDACTED]"
        elif isinstance(value, bytes):
            safe[key] = f"hex:{value.hex()}"
        elif isinstance(value, dict):
            safe[key] = _redact_sensitive_payload(value)
        elif isinstance(value, (list, tuple)):
            safe[key] = [
                _redact_sensitive_payload(v) if isinstance(v, dict) else v
                for v in value
            ]
        else:
            safe[key] = value
    return safe


def validate_operation_id(operation_id: str) -> str:
    """Validates that operation_id is non-empty, non-whitespace, and bounded."""
    if not isinstance(operation_id, str):
        raise ValueError(f"operation_id must be a string, got {type(operation_id).__name__}")
    op = operation_id.strip()
    if not op or len(op) > 128:
        raise ValueError(f"operation_id must be a non-empty string <= 128 chars, got {operation_id!r}")
    return op


def create_phase9_audit_event(
    *,
    operation_id: str,
    actor_id: UUID,
    action: str,
    event_type: AuditEventType,
    aggregate_type: str = "phase9_security",
    resource_id: str | None = None,
    payload: Mapping[str, Any] | None = None,
    recorded_at: datetime | None = None,
) -> AuditEvent:
    """Creates a deterministic D16-E22 PHASE9_MUTATION audit event envelope."""
    op_id = validate_operation_id(operation_id)
    if event_type not in (
        AuditEventType.PHASE9_MUTATION_INTENT,
        AuditEventType.PHASE9_MUTATION_APPLIED,
        AuditEventType.PHASE9_MUTATION_REJECTED,
        AuditEventType.PHASE9_MUTATION_FAILED,
    ):
        raise ValueError(f"Invalid Phase 9 mutation event type: {event_type}")

    safe_payload = _redact_sensitive_payload(payload or {})
    full_payload = {
        "operation_id": op_id,
        "action": action,
        "resource_id": resource_id,
        **safe_payload,
    }
    payload_json = canonical_json_dumps(full_payload)

    event_id = derive_audit_event_id(
        event_family=AuditEventFamily.PHASE9_MUTATION,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_identity=str(actor_id),
        canonical_domain_identity=f"{op_id}:{event_type.value}",
        payload_json=payload_json,
    )

    rec_time = recorded_at or recorded_at_utc_now()
    return AuditEvent(
        event_id=event_id,
        event_family=AuditEventFamily.PHASE9_MUTATION.value,
        event_type=event_type.value,
        aggregate_type=aggregate_type,
        aggregate_identity=str(actor_id),
        recorded_at_utc=rec_time,
        payload_json=payload_json,
    )


class Phase9MutationCoordinator:
    """Coordinates staged mutation, intent, commit, and applied outbox transitions."""

    def __init__(self, *, audit_store: CoreAuditAppendAuthority) -> None:
        self._audit_store = audit_store

    def execute(
        self,
        *,
        operation_id: str,
        actor_id: UUID,
        action: str,
        aggregate_type: str,
        resource_id: str | None,
        payload: Mapping[str, Any] | None,
        outbox_save_fn: Callable[[str, UUID, str, str | None, str, str, str | None, str | None, str | None], None],
        outbox_update_fn: Callable[[str, str, str | None, str | None], None],
        outbox_get_fn: Callable[[str], sqlite3.Row | dict[str, Any] | None],
        stage_fn: Callable[[], None] | None,
        commit_fn: Callable[[], Any],
    ) -> Any:
        """Executes the 4-phase mutation protocol with fail-closed recovery semantics."""
        op_id = validate_operation_id(operation_id)
        safe_payload = _redact_sensitive_payload(payload or {})
        payload_json = canonical_json_dumps(safe_payload)

        # 0. Check outbox for idempotency / prior state
        existing = outbox_get_fn(op_id)
        if existing is not None:
            state = existing["stage_state"] if isinstance(existing, sqlite3.Row) or isinstance(existing, dict) else getattr(existing, "stage_state", None)
            existing_user = str(existing["user_id"] if "user_id" in existing.keys() else existing["owner_id"])
            if existing_user != str(actor_id):
                raise ValueError(f"operation_id {op_id!r} was created for a different actor")
            if existing["action"] != action:
                raise ValueError(f"operation_id {op_id!r} was created for a different action")

            if state == OutboxStageState.VERIFIED_APPLIED.value:
                # Already verified and applied -> idempotent success
                return {"operation_id": op_id, "status": "VERIFIED_APPLIED", "already_applied": True}

            if state == OutboxStageState.COMMITTED_PENDING_AUDIT.value:
                # Local business mutation is ALREADY COMMITTED. Do NOT repeat commit_fn!
                applied_event = create_phase9_audit_event(
                    operation_id=op_id,
                    actor_id=actor_id,
                    action=action,
                    event_type=AuditEventType.PHASE9_MUTATION_APPLIED,
                    aggregate_type=aggregate_type,
                    resource_id=resource_id,
                    payload=safe_payload,
                )
                try:
                    persisted = self._audit_store.append_audit_events([applied_event])
                    if len(persisted) == 1:
                        outbox_update_fn(op_id, OutboxStageState.VERIFIED_APPLIED.value, persisted[0].event_id, None)
                        return {"operation_id": op_id, "status": "VERIFIED_APPLIED", "reconciled": True}
                except Exception as exc:
                    raise RuntimeError(f"local mutation committed; audit outcome delivery pending: {exc}") from exc

            if state == OutboxStageState.REJECTED.value:
                raise ValueError(f"operation_id {op_id!r} was previously rejected: {existing.get('error_message')}")
            if state == OutboxStageState.FAILED.value:
                raise RuntimeError(f"operation_id {op_id!r} was previously failed: {existing.get('error_message')}")

        # 1. LOCAL STAGE
        if stage_fn is not None:
            stage_fn()
        outbox_save_fn(op_id, actor_id, action, resource_id, payload_json, OutboxStageState.STAGED.value, None, None, None)

        # 2. PHASE9_MUTATION_INTENT
        intent_event = create_phase9_audit_event(
            operation_id=op_id,
            actor_id=actor_id,
            action=action,
            event_type=AuditEventType.PHASE9_MUTATION_INTENT,
            aggregate_type=aggregate_type,
            resource_id=resource_id,
            payload=safe_payload,
        )
        try:
            persisted_intent = self._audit_store.append_audit_events([intent_event])
            if len(persisted_intent) != 1:
                raise RuntimeError("intent audit append returned no evidence")
            intent_event_id = persisted_intent[0].event_id
        except Exception as exc:
            # Audit delivery failed before intent recorded -> fail closed
            outbox_update_fn(op_id, OutboxStageState.FAILED.value, None, f"intent audit append failed: {exc}")
            raise RuntimeError(f"authoritative core audit intent append failed: {exc}") from exc

        outbox_update_fn(op_id, OutboxStageState.INTENT_RECORDED.value, None, None)

        # 3. AUDIT-AUTHORIZED LOCAL EFFECTIVE COMMIT
        result = None
        try:
            result = commit_fn()
            outbox_update_fn(op_id, OutboxStageState.COMMITTED_PENDING_AUDIT.value, None, None)
        except (ValueError, TypeError, PermissionError) as rej_exc:
            # Policy or validation rejection
            outbox_update_fn(op_id, OutboxStageState.REJECTED.value, None, str(rej_exc))
            try:
                rej_event = create_phase9_audit_event(
                    operation_id=op_id,
                    actor_id=actor_id,
                    action=action,
                    event_type=AuditEventType.PHASE9_MUTATION_REJECTED,
                    aggregate_type=aggregate_type,
                    resource_id=resource_id,
                    payload={**safe_payload, "rejection_reason": str(rej_exc)},
                )
                self._audit_store.append_audit_events([rej_event])
            except Exception:
                pass
            raise rej_exc
        except Exception as exec_exc:
            # Execution or database failure
            outbox_update_fn(op_id, OutboxStageState.FAILED.value, None, str(exec_exc))
            try:
                failed_event = create_phase9_audit_event(
                    operation_id=op_id,
                    actor_id=actor_id,
                    action=action,
                    event_type=AuditEventType.PHASE9_MUTATION_FAILED,
                    aggregate_type=aggregate_type,
                    resource_id=resource_id,
                    payload={**safe_payload, "error": str(exec_exc)},
                )
                self._audit_store.append_audit_events([failed_event])
            except Exception:
                pass
            raise exec_exc

        # 4. PHASE9_MUTATION_APPLIED
        applied_event = create_phase9_audit_event(
            operation_id=op_id,
            actor_id=actor_id,
            action=action,
            event_type=AuditEventType.PHASE9_MUTATION_APPLIED,
            aggregate_type=aggregate_type,
            resource_id=resource_id,
            payload=safe_payload,
        )
        try:
            persisted_applied = self._audit_store.append_audit_events([applied_event])
            if len(persisted_applied) != 1:
                raise RuntimeError("applied audit append returned no evidence")
            applied_event_id = persisted_applied[0].event_id
            outbox_update_fn(op_id, OutboxStageState.VERIFIED_APPLIED.value, applied_event_id, None)
        except Exception as audit_exc:
            # Local mutation was effective, but applied audit delivery failed -> OUTCOME_PENDING
            # Do NOT rollback or re-execute business mutation
            raise RuntimeError(f"local mutation effective; audit outcome delivery pending: {audit_exc}") from audit_exc

        return result


class MandatoryCoreSecurityAudit:
    """Security audit authority writing to Core Audit via transactional outbox protocol."""

    def __init__(self, *, audit_store: CoreAuditAppendAuthority, security_store: Any) -> None:
        self._audit_store = audit_store
        self._security_store = security_store
        self._coordinator = Phase9MutationCoordinator(audit_store=audit_store)

    def record(
        self,
        *,
        actor_id: UUID,
        action: str,
        payload: Mapping[str, Any] | None = None,
        rejected: bool = False,
        operation_id: str | None = None,
        resource_id: str | None = None,
    ) -> str:
        """Standalone or observed security audit recording."""
        op_id = validate_operation_id(operation_id or str(uuid4()))
        event_type = (
            AuditEventType.PHASE9_MUTATION_REJECTED
            if rejected
            else AuditEventType.PHASE9_MUTATION_APPLIED
        )
        event = create_phase9_audit_event(
            operation_id=op_id,
            actor_id=actor_id,
            action=action,
            event_type=event_type,
            aggregate_type="phase9_security",
            resource_id=resource_id,
            payload=payload,
        )
        persisted = self._audit_store.append_audit_events([event])
        if len(persisted) != 1:
            raise RuntimeError("authoritative audit append did not return evidence")
        reference = persisted[0].event_id
        if self._security_store is not None and hasattr(self._security_store, "save_audit_reference"):
            self._security_store.save_audit_reference(event_id=reference, user_id=actor_id, action=action)
        return reference

    def create_owner_bootstrap(
        self,
        *,
        actor_id: UUID,
        expires_at: datetime,
        operation_id: str | None = None,
    ) -> str:
        """Trusted-host bootstrap creation executed via audited outbox protocol."""
        op_id = validate_operation_id(operation_id or str(uuid4()))

        def stage():
            # Check if owner already has credential
            if self._security_store._conn.execute(
                "SELECT 1 FROM webauthn_credentials WHERE user_id = ? AND enabled = 1 AND revoked = 0",
                (str(actor_id),),
            ).fetchone():
                raise RuntimeError("owner already has a credential; bootstrap forbidden")

        def commit():
            return self._security_store.create_owner_bootstrap(user_id=actor_id, expires_at=expires_at)

        return self._coordinator.execute(
            operation_id=op_id,
            actor_id=actor_id,
            action="WEBAUTHN_BOOTSTRAP_CREATION",
            aggregate_type="phase9_security",
            resource_id=str(actor_id),
            payload={"expires_at_utc": expires_at.isoformat()},
            outbox_save_fn=self._security_store.save_outbox_stage,
            outbox_update_fn=self._security_store.update_outbox_state,
            outbox_get_fn=self._security_store.get_outbox_record,
            stage_fn=stage,
            commit_fn=commit,
        )

    def reconcile_pending_outbox(self) -> int:
        """Reconciles subordinate store outbox rows in COMMITTED_PENDING_AUDIT state."""
        if not hasattr(self._security_store, "get_pending_outbox_records"):
            return 0
        pending = self._security_store.get_pending_outbox_records()
        reconciled = 0
        for row in pending:
            op_id = row["operation_id"]
            user_id = UUID(row["user_id"])
            action = row["action"]
            payload = json.loads(row["payload_json"])
            applied_event = create_phase9_audit_event(
                operation_id=op_id,
                actor_id=user_id,
                action=action,
                event_type=AuditEventType.PHASE9_MUTATION_APPLIED,
                aggregate_type="phase9_security",
                resource_id=row["resource_id"],
                payload=payload,
            )
            try:
                persisted = self._audit_store.append_audit_events([applied_event])
                if len(persisted) == 1:
                    self._security_store.update_outbox_state(
                        op_id, OutboxStageState.VERIFIED_APPLIED.value, persisted[0].event_id, None
                    )
                    reconciled += 1
            except Exception:
                pass
        return reconciled
