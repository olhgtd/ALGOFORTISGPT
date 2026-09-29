"""Durable Owner/Admin + AI control-plane repository.

All state lives in the existing security SQLite authority.  This module does
not create a second audit database and does not expose trading/broker mutation.
Secrets are never stored here; provider credentials are represented only by
opaque credential references owned by the approved secret provider.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID, uuid4


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class OwnerAdminRepository:
    """Additive tables inside the existing security-store authority."""

    def __init__(self, security_store: Any) -> None:
        if security_store is None or not hasattr(security_store, "_transaction"):
            raise RuntimeError("durable security authority unavailable")
        self._store = security_store
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._store._transaction() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS owner_step_up_challenges (
                challenge_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                action_family TEXT NOT NULL,
                resource_ref TEXT,
                expires_at_utc TEXT NOT NULL,
                consumed_at_utc TEXT,
                created_at_utc TEXT NOT NULL
            )""")
            cur.execute("""CREATE TABLE IF NOT EXISTS owner_step_up_grants (
                grant_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                action_family TEXT NOT NULL,
                resource_ref TEXT,
                expires_at_utc TEXT NOT NULL,
                consumed_at_utc TEXT,
                created_at_utc TEXT NOT NULL
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_owner_step_up_grants_user ON owner_step_up_grants(user_id)")
            cur.execute("""CREATE TABLE IF NOT EXISTS owner_admin_incidents (
                incident_id TEXT PRIMARY KEY,
                actor_id TEXT NOT NULL,
                action_family TEXT NOT NULL,
                resource_ref TEXT,
                reason_code TEXT NOT NULL,
                status TEXT NOT NULL,
                details_json TEXT NOT NULL,
                core_audit_ref TEXT,
                created_at_utc TEXT NOT NULL
            )""")
            cur.execute("""CREATE TABLE IF NOT EXISTS ai_agents (
                agent_id TEXT PRIMARY KEY,
                role_type TEXT NOT NULL,
                display_name TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                authority_state TEXT NOT NULL,
                config_version INTEGER NOT NULL,
                updated_at_utc TEXT NOT NULL
            )""")
            cur.execute("""CREATE TABLE IF NOT EXISTS ai_providers (
                provider_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                provider_type TEXT NOT NULL,
                credential_ref TEXT,
                enabled INTEGER NOT NULL,
                authority_state TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            )""")
            cur.execute("""CREATE TABLE IF NOT EXISTS ai_models (
                model_id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                capability TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                authority_state TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            )""")
            cur.execute("""CREATE TABLE IF NOT EXISTS ai_agent_bindings (
                agent_id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                fallback_policy_json TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            )""")
            cur.execute("""CREATE TABLE IF NOT EXISTS ai_jobs (
                job_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                job_type TEXT NOT NULL,
                scope TEXT NOT NULL,
                status TEXT NOT NULL,
                request_json TEXT NOT NULL,
                output_json TEXT,
                provider_id TEXT,
                model_id TEXT,
                evidence_ref TEXT,
                failure_reason TEXT,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_jobs_created ON ai_jobs(created_at_utc DESC)")
            cur.execute("""CREATE TABLE IF NOT EXISTS ai_artifacts (
                artifact_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                artifact_ref TEXT NOT NULL,
                sha256 TEXT,
                evidence_ref TEXT,
                created_at_utc TEXT NOT NULL
            )""")

            now = _iso(_utc_now())
            for agent_id, role_type, display_name in (
                ("prime", "PRIME", "Prime Agent"),
                ("laya", "LAYA", "Laya Market Intelligence"),
                ("research", "RESEARCH", "Research Agent"),
                ("risk-challenger", "RISK_CHALLENGER", "Risk Challenger"),
            ):
                cur.execute(
                    """INSERT OR IGNORE INTO ai_agents(
                        agent_id, role_type, display_name, enabled, authority_state,
                        config_version, updated_at_utc
                    ) VALUES (?, ?, ?, 1, 'UNKNOWN', 1, ?)""",
                    (agent_id, role_type, display_name, now),
                )

    # ------------------------------------------------------------------
    # Step-up proof state
    # ------------------------------------------------------------------
    def save_step_up_challenge(
        self,
        *,
        challenge_id: str,
        user_id: UUID,
        action_family: str,
        resource_ref: str | None,
        expires_at: datetime,
    ) -> None:
        now = _iso(_utc_now())
        with self._store._transaction() as cur:
            cur.execute(
                """INSERT OR REPLACE INTO owner_step_up_challenges(
                    challenge_id, user_id, action_family, resource_ref,
                    expires_at_utc, consumed_at_utc, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, NULL, ?)""",
                (challenge_id, str(user_id), action_family, resource_ref, _iso(expires_at), now),
            )

    def consume_step_up_challenge(
        self,
        *,
        challenge_id: str,
        user_id: UUID,
        action_family: str,
        resource_ref: str | None,
        now: datetime,
    ) -> None:
        with self._store._transaction() as cur:
            row = cur.execute(
                "SELECT * FROM owner_step_up_challenges WHERE challenge_id = ?",
                (challenge_id,),
            ).fetchone()
            if row is None:
                raise PermissionError("step-up challenge unavailable")
            if row["user_id"] != str(user_id) or row["action_family"] != action_family:
                raise PermissionError("step-up challenge scope mismatch")
            if (row["resource_ref"] or None) != (resource_ref or None):
                raise PermissionError("step-up challenge resource mismatch")
            if row["consumed_at_utc"] is not None or now > _dt(row["expires_at_utc"]):
                raise PermissionError("step-up challenge expired or already consumed")
            cur.execute(
                "UPDATE owner_step_up_challenges SET consumed_at_utc = ? WHERE challenge_id = ?",
                (_iso(now), challenge_id),
            )

    @staticmethod
    def grant_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_step_up_grant(
        self,
        *,
        user_id: UUID,
        action_family: str,
        resource_ref: str | None,
        expires_at: datetime,
    ) -> str:
        token = "af_su_" + secrets.token_urlsafe(36)
        with self._store._transaction() as cur:
            cur.execute(
                """INSERT INTO owner_step_up_grants(
                    grant_hash, user_id, action_family, resource_ref,
                    expires_at_utc, consumed_at_utc, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, NULL, ?)""",
                (
                    self.grant_hash(token), str(user_id), action_family, resource_ref,
                    _iso(expires_at), _iso(_utc_now()),
                ),
            )
        return token

    def consume_step_up_grant(
        self,
        *,
        token: str,
        user_id: UUID,
        action_family: str,
        resource_ref: str | None,
        now: datetime,
    ) -> str:
        digest = self.grant_hash(token)
        with self._store._transaction() as cur:
            row = cur.execute(
                "SELECT * FROM owner_step_up_grants WHERE grant_hash = ?",
                (digest,),
            ).fetchone()
            if row is None:
                raise PermissionError("step-up grant unavailable")
            if row["user_id"] != str(user_id) or row["action_family"] != action_family:
                raise PermissionError("step-up grant scope mismatch")
            if (row["resource_ref"] or None) != (resource_ref or None):
                raise PermissionError("step-up grant resource mismatch")
            if row["consumed_at_utc"] is not None or now > _dt(row["expires_at_utc"]):
                raise PermissionError("step-up grant expired or already consumed")
            cur.execute(
                "UPDATE owner_step_up_grants SET consumed_at_utc = ? WHERE grant_hash = ?",
                (_iso(now), digest),
            )
        return digest[:16]

    # ------------------------------------------------------------------
    # Incident evidence subordinate to Core Audit
    # ------------------------------------------------------------------
    def save_incident(
        self,
        *,
        actor_id: UUID,
        action_family: str,
        resource_ref: str | None,
        reason_code: str,
        status: str,
        details: Mapping[str, Any] | None,
        core_audit_ref: str | None,
    ) -> str:
        incident_id = "inc_" + uuid4().hex
        safe = dict(details or {})
        with self._store._transaction() as cur:
            cur.execute(
                """INSERT INTO owner_admin_incidents(
                    incident_id, actor_id, action_family, resource_ref, reason_code,
                    status, details_json, core_audit_ref, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    incident_id, str(actor_id), action_family, resource_ref, reason_code,
                    status, json.dumps(safe, sort_keys=True, separators=(",", ":")),
                    core_audit_ref, _iso(_utc_now()),
                ),
            )
        return incident_id

    def list_incidents(self, *, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        rows = self._store._conn.execute(
            "SELECT * FROM owner_admin_incidents ORDER BY created_at_utc DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # AI registry / job evidence (research-shadow only)
    # ------------------------------------------------------------------
    def list_agents(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._store._conn.execute(
            "SELECT * FROM ai_agents ORDER BY agent_id"
        ).fetchall()]

    def set_agent_enabled(self, *, agent_id: str, enabled: bool, state: str | None = None) -> dict[str, Any]:
        with self._store._transaction() as cur:
            row = cur.execute("SELECT * FROM ai_agents WHERE agent_id = ?", (agent_id,)).fetchone()
            if row is None:
                raise ValueError("unknown AI agent")
            next_state = state or row["authority_state"]
            cur.execute(
                """UPDATE ai_agents SET enabled = ?, authority_state = ?,
                   config_version = config_version + 1, updated_at_utc = ? WHERE agent_id = ?""",
                (int(enabled), next_state, _iso(_utc_now()), agent_id),
            )
        return dict(self._store._conn.execute("SELECT * FROM ai_agents WHERE agent_id = ?", (agent_id,)).fetchone())

    def upsert_provider(
        self,
        *,
        provider_id: str,
        display_name: str,
        provider_type: str,
        credential_ref: str | None,
        enabled: bool,
        authority_state: str,
    ) -> dict[str, Any]:
        with self._store._transaction() as cur:
            cur.execute(
                """INSERT INTO ai_providers(provider_id, display_name, provider_type,
                   credential_ref, enabled, authority_state, updated_at_utc)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(provider_id) DO UPDATE SET
                     display_name=excluded.display_name,
                     provider_type=excluded.provider_type,
                     credential_ref=excluded.credential_ref,
                     enabled=excluded.enabled,
                     authority_state=excluded.authority_state,
                     updated_at_utc=excluded.updated_at_utc""",
                (
                    provider_id, display_name, provider_type, credential_ref,
                    int(enabled), authority_state, _iso(_utc_now()),
                ),
            )
        return dict(self._store._conn.execute("SELECT * FROM ai_providers WHERE provider_id = ?", (provider_id,)).fetchone())

    def list_providers(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._store._conn.execute(
            "SELECT * FROM ai_providers ORDER BY provider_id"
        ).fetchall()]

    def upsert_model(
        self,
        *,
        model_id: str,
        provider_id: str,
        display_name: str,
        capability: str,
        enabled: bool,
        authority_state: str,
    ) -> dict[str, Any]:
        provider = self._store._conn.execute(
            "SELECT provider_id FROM ai_providers WHERE provider_id = ?", (provider_id,)
        ).fetchone()
        if provider is None:
            raise ValueError("AI provider unavailable")
        with self._store._transaction() as cur:
            cur.execute(
                """INSERT INTO ai_models(model_id, provider_id, display_name, capability,
                   enabled, authority_state, updated_at_utc)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(model_id) DO UPDATE SET
                     provider_id=excluded.provider_id,
                     display_name=excluded.display_name,
                     capability=excluded.capability,
                     enabled=excluded.enabled,
                     authority_state=excluded.authority_state,
                     updated_at_utc=excluded.updated_at_utc""",
                (
                    model_id, provider_id, display_name, capability,
                    int(enabled), authority_state, _iso(_utc_now()),
                ),
            )
        return dict(self._store._conn.execute("SELECT * FROM ai_models WHERE model_id = ?", (model_id,)).fetchone())

    def list_models(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._store._conn.execute(
            "SELECT * FROM ai_models ORDER BY provider_id, model_id"
        ).fetchall()]

    def set_binding(
        self,
        *,
        agent_id: str,
        provider_id: str,
        model_id: str,
        fallback_policy: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        agent = self._store._conn.execute("SELECT 1 FROM ai_agents WHERE agent_id = ?", (agent_id,)).fetchone()
        model = self._store._conn.execute(
            "SELECT provider_id FROM ai_models WHERE model_id = ?", (model_id,)
        ).fetchone()
        if agent is None or model is None or model["provider_id"] != provider_id:
            raise ValueError("invalid AI binding")
        policy_json = json.dumps(dict(fallback_policy or {"mode": "FAIL_CLOSED"}), sort_keys=True, separators=(",", ":"))
        with self._store._transaction() as cur:
            cur.execute(
                """INSERT INTO ai_agent_bindings(agent_id, provider_id, model_id,
                   fallback_policy_json, updated_at_utc) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(agent_id) DO UPDATE SET
                     provider_id=excluded.provider_id,
                     model_id=excluded.model_id,
                     fallback_policy_json=excluded.fallback_policy_json,
                     updated_at_utc=excluded.updated_at_utc""",
                (agent_id, provider_id, model_id, policy_json, _iso(_utc_now())),
            )
        return dict(self._store._conn.execute("SELECT * FROM ai_agent_bindings WHERE agent_id = ?", (agent_id,)).fetchone())

    def get_binding(self, agent_id: str) -> dict[str, Any] | None:
        row = self._store._conn.execute(
            "SELECT * FROM ai_agent_bindings WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def list_bindings(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._store._conn.execute(
            "SELECT * FROM ai_agent_bindings ORDER BY agent_id"
        ).fetchall()]

    def create_job(
        self,
        *,
        agent_id: str,
        job_type: str,
        scope: str,
        request: Mapping[str, Any],
        status: str,
        provider_id: str | None = None,
        model_id: str | None = None,
        failure_reason: str | None = None,
        evidence_ref: str | None = None,
    ) -> dict[str, Any]:
        job_id = "aij_" + uuid4().hex
        now = _iso(_utc_now())
        with self._store._transaction() as cur:
            cur.execute(
                """INSERT INTO ai_jobs(job_id, agent_id, job_type, scope, status,
                   request_json, output_json, provider_id, model_id, evidence_ref,
                   failure_reason, created_at_utc, updated_at_utc)
                   VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id, agent_id, job_type, scope, status,
                    json.dumps(dict(request), sort_keys=True, separators=(",", ":")),
                    provider_id, model_id, evidence_ref, failure_reason, now, now,
                ),
            )
        return self.get_job(job_id) or {}

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        row = self._store._conn.execute("SELECT * FROM ai_jobs WHERE job_id = ?", (job_id,)).fetchone()
        return dict(row) if row is not None else None

    def list_jobs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        return [dict(row) for row in self._store._conn.execute(
            "SELECT * FROM ai_jobs ORDER BY created_at_utc DESC LIMIT ?", (limit,)
        ).fetchall()]

    def update_job(
        self,
        *,
        job_id: str,
        status: str,
        output: Mapping[str, Any] | None = None,
        evidence_ref: str | None = None,
        failure_reason: str | None = None,
    ) -> dict[str, Any]:
        if self.get_job(job_id) is None:
            raise ValueError("AI job unavailable")
        with self._store._transaction() as cur:
            cur.execute(
                """UPDATE ai_jobs SET status = ?, output_json = ?, evidence_ref = ?,
                   failure_reason = ?, updated_at_utc = ? WHERE job_id = ?""",
                (
                    status,
                    json.dumps(dict(output), sort_keys=True, separators=(",", ":")) if output is not None else None,
                    evidence_ref, failure_reason, _iso(_utc_now()), job_id,
                ),
            )
        return self.get_job(job_id) or {}
