"""Owner-only Decision Intelligence controls inside the existing admin authority.

This is an additive router under the authoritative Owner/Admin namespace.  It
reuses the existing session authority, security SQLite authority, AI control
service and global Owner step-up middleware.  It creates no trading, broker,
identity, accounting, or RiskGate authority.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from dashboard.backend.account_v2.contracts import IntelligenceCapability
from dashboard.backend.account_v2.intelligence_entitlements import (
    IntelligenceEntitlementService,
    SQLiteIntelligenceEntitlementStore,
)
from engine.ai.monitoring_scheduler_v2 import (
    MarketWatchPolicyV2,
    MonitoringTaskClass,
    MonitoringTriggerType,
)
from engine.ai.provider_queue_v2 import ProviderQueuePolicyV2
from engine.ai.scope_expansion_v2 import ScopeExpansionRequest


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MarketWatchPolicyBody(BaseModel):
    policy_ref: str = Field(min_length=1, max_length=160)
    policy_version: str = Field(default="1.0.0", max_length=40)
    allowed_instruments: list[str] = Field(min_length=1, max_length=100)
    frequency_seconds: int = Field(gt=0, le=86400)
    task_ttl_seconds: int = Field(gt=0, le=86400)
    provider_id: str = Field(min_length=1, max_length=120)
    model_id: str = Field(min_length=1, max_length=160)
    allowed_trigger_types: list[str] = Field(default_factory=lambda: ["SCHEDULED"])
    allowed_task_classes: list[str] = Field(default_factory=lambda: ["SCHEDULED_MONITORING"])
    allowed_timeframes: list[str] = Field(default_factory=lambda: ["5m"])
    strategy_review_mode: str = Field(default="OPTIONAL", max_length=20)
    independent_candidate_scan: bool = False


class StrategyHuntingBody(BaseModel):
    enabled: bool
    data_policy_ref: str | None = Field(default=None, max_length=200)


class ProviderQueueBody(BaseModel):
    policy_ref: str = Field(min_length=1, max_length=160)
    provider_id: str = Field(min_length=1, max_length=120)
    max_concurrency: int = Field(gt=0, le=100)
    max_queue_size: int = Field(gt=0, le=10000)
    retry_after_seconds: int = Field(ge=0, le=86400)
    allowed_fallback_provider_ids: list[str] = Field(default_factory=list, max_length=100)
    max_requests_per_window: int | None = Field(default=None, gt=0, le=100000)
    window_seconds: int = Field(default=60, gt=0, le=86400)


class EntitlementBody(BaseModel):
    capabilities: list[str] = Field(default_factory=list, max_length=20)


class ScopeDecisionBody(BaseModel):
    decision: str = Field(pattern="^(APPROVE|DENY)$")


class DecisionIntelligenceConfigStore:
    """Versioned config rows inside the existing security SQLite authority."""

    def __init__(self, security_store: Any) -> None:
        if security_store is None or not hasattr(security_store, "_transaction") or not hasattr(security_store, "_conn"):
            raise RuntimeError("security authority unavailable")
        self._store = security_store
        with self._store._transaction() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS ai_decision_intelligence_config (
                    config_key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    updated_at_utc TEXT NOT NULL
                )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS ai_scope_expansion_requests (
                    request_id TEXT PRIMARY KEY,
                    requested_by TEXT NOT NULL,
                    expansion_type TEXT NOT NULL,
                    requested_value TEXT NOT NULL,
                    reason_ref TEXT NOT NULL,
                    requested_at_utc TEXT NOT NULL,
                    policy_ref TEXT NOT NULL,
                    status TEXT NOT NULL,
                    decided_at_utc TEXT
                )"""
            )

    def put(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
        with self._store._transaction() as cur:
            row = cur.execute(
                "SELECT version FROM ai_decision_intelligence_config WHERE config_key = ?",
                (key,),
            ).fetchone()
            version = int(row["version"]) + 1 if row is not None else 1
            cur.execute(
                """INSERT INTO ai_decision_intelligence_config(config_key, value_json, version, updated_at_utc)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(config_key) DO UPDATE SET
                     value_json=excluded.value_json,
                     version=excluded.version,
                     updated_at_utc=excluded.updated_at_utc""",
                (key, encoded, version, _now()),
            )
        return {"config_key": key, "version": version, "value": value}

    def get(self, key: str) -> dict[str, Any] | None:
        row = self._store._conn.execute(
            "SELECT value_json, version, updated_at_utc FROM ai_decision_intelligence_config WHERE config_key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return {
            "config_key": key,
            "version": int(row["version"]),
            "updated_at_utc": row["updated_at_utc"],
            "value": json.loads(row["value_json"]),
        }

    def record_scope_request(self, request: ScopeExpansionRequest) -> None:
        if not isinstance(request, ScopeExpansionRequest):
            raise TypeError("request must be ScopeExpansionRequest")
        with self._store._transaction() as cur:
            cur.execute(
                """INSERT OR IGNORE INTO ai_scope_expansion_requests(
                    request_id, requested_by, expansion_type, requested_value,
                    reason_ref, requested_at_utc, policy_ref, status, decided_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)""",
                (
                    request.request_id,
                    request.requested_by,
                    request.expansion_type.value,
                    request.requested_value,
                    request.reason_ref,
                    request.requested_at.astimezone(timezone.utc).isoformat(),
                    request.policy_ref,
                    request.status,
                ),
            )

    def list_scope_requests(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self._store._conn.execute(
                "SELECT * FROM ai_scope_expansion_requests ORDER BY requested_at_utc DESC"
            ).fetchall()
        ]

    def decide_scope_request(self, request_id: str, decision: str) -> dict[str, Any]:
        status = "OWNER_APPROVED" if decision == "APPROVE" else "OWNER_DENIED"
        with self._store._transaction() as cur:
            row = cur.execute(
                "SELECT * FROM ai_scope_expansion_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if row is None:
                raise LookupError("scope request unavailable")
            if row["status"] != "PENDING_OWNER_REVIEW":
                raise ValueError("scope request already decided")
            cur.execute(
                "UPDATE ai_scope_expansion_requests SET status = ?, decided_at_utc = ? WHERE request_id = ?",
                (status, _now(), request_id),
            )
        return dict(
            self._store._conn.execute(
                "SELECT * FROM ai_scope_expansion_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        )


def _owner_session(app: Any, request: Request):
    authorization = request.headers.get("authorization")
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    try:
        session = app.state.sessions.require(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="authentication required") from exc
    role = getattr(getattr(session, "user", None), "role", None)
    role_value = getattr(role, "value", role)
    account_status = getattr(getattr(session, "user", None), "account_status", None)
    account_value = getattr(account_status, "value", account_status)
    if role_value != "OWNER" or account_value != "ACTIVE":
        raise HTTPException(status_code=403, detail="active owner authority required")
    return session


def _policy_payload(policy: MarketWatchPolicyV2) -> dict[str, Any]:
    return {
        "policy_ref": policy.policy_ref,
        "policy_version": policy.policy_version,
        "allowed_instruments": list(policy.allowed_instruments),
        "frequency_seconds": policy.frequency_seconds,
        "task_ttl_seconds": policy.task_ttl_seconds,
        "provider_id": policy.provider_id,
        "model_id": policy.model_id,
        "allowed_trigger_types": [item.value for item in policy.allowed_trigger_types],
        "allowed_task_classes": [item.value for item in policy.allowed_task_classes],
        "allowed_timeframes": list(policy.allowed_timeframes),
        "strategy_review_mode": policy.strategy_review_mode,
        "independent_candidate_scan": policy.independent_candidate_scan,
    }


def _queue_payload(policy: ProviderQueuePolicyV2) -> dict[str, Any]:
    return {
        "policy_ref": policy.policy_ref,
        "provider_id": policy.provider_id,
        "max_concurrency": policy.max_concurrency,
        "max_queue_size": policy.max_queue_size,
        "retry_after_seconds": policy.retry_after_seconds,
        "allowed_fallback_provider_ids": list(policy.allowed_fallback_provider_ids),
        "max_requests_per_window": policy.max_requests_per_window,
        "window_seconds": policy.window_seconds,
    }


def attach_owner_decision_intelligence(app: Any) -> Any:
    if getattr(app.state, "owner_decision_intelligence_attached", False):
        return app
    security_store = getattr(app.state, "security_store", None)
    if security_store is None:
        app.state.owner_decision_intelligence_attached = False
        return app

    config = DecisionIntelligenceConfigStore(security_store)
    entitlements = IntelligenceEntitlementService(SQLiteIntelligenceEntitlementStore(security_store))
    app.state.decision_intelligence_config = config
    app.state.intelligence_entitlements = entitlements
    app.state.owner_decision_intelligence_attached = True

    router = APIRouter(prefix="/api/v1/owner/admin/ai/intelligence", tags=["owner-ai-decision-intelligence"])

    @router.get("")
    def snapshot(request: Request) -> dict[str, Any]:
        _owner_session(app, request)
        ai_control = getattr(app.state, "ai_control", None)
        ai_snapshot = ai_control.snapshot() if ai_control is not None and hasattr(ai_control, "snapshot") else {
            "authority_state": "UNAVAILABLE",
            "agents": [], "providers": [], "models": [], "jobs": [],
        }
        arbitrator = getattr(app.state, "portfolio_candidate_arbitrator", None)
        try:
            portfolio = {
                "authority_state": "AVAILABLE",
                "aggregate_reserved": str(arbitrator.total_reserved),
                "source": "engine/portfolio/",
            } if arbitrator is not None else {
                "authority_state": "UNAVAILABLE",
                "source": "engine/portfolio/",
            }
        except Exception:
            portfolio = {"authority_state": "UNAVAILABLE", "source": "engine/portfolio/"}
        return {
            **ai_snapshot,
            "live_state": "READ_ONLY/DISARMED",
            "broker_mutation": "ABSENT",
            "risk_authority": "RiskGateV2",
            "market_watch_policy": config.get("market_watch_policy"),
            "strategy_hunting": config.get("strategy_hunting"),
            "provider_queue": config.get("provider_queue"),
            "scope_requests": config.list_scope_requests(),
            "candidate_portfolio": portfolio,
            "entitlement_authority": "S2_DEVICE_SESSION_PLUS_CAPABILITY",
        }

    @router.post("/market-watch-policy")
    def set_market_watch_policy(body: MarketWatchPolicyBody, request: Request) -> dict[str, Any]:
        _owner_session(app, request)
        policy = MarketWatchPolicyV2(
            policy_ref=body.policy_ref,
            policy_version=body.policy_version,
            allowed_instruments=tuple(body.allowed_instruments),
            frequency_seconds=body.frequency_seconds,
            task_ttl_seconds=body.task_ttl_seconds,
            provider_id=body.provider_id,
            model_id=body.model_id,
            allowed_trigger_types=tuple(MonitoringTriggerType(item) for item in body.allowed_trigger_types),
            allowed_task_classes=tuple(MonitoringTaskClass(item) for item in body.allowed_task_classes),
            allowed_timeframes=tuple(body.allowed_timeframes),
            strategy_review_mode=body.strategy_review_mode,
            independent_candidate_scan=body.independent_candidate_scan,
        )
        return config.put("market_watch_policy", _policy_payload(policy))

    @router.post("/strategy-hunting")
    def set_strategy_hunting(body: StrategyHuntingBody, request: Request) -> dict[str, Any]:
        _owner_session(app, request)
        return config.put(
            "strategy_hunting",
            {
                "enabled": body.enabled,
                "data_policy_ref": body.data_policy_ref,
                "od16_required": True,
                "execution_scope": "RISK_GATED_CANDIDATE",
            },
        )

    @router.post("/provider-queue")
    def set_provider_queue(body: ProviderQueueBody, request: Request) -> dict[str, Any]:
        _owner_session(app, request)
        policy = ProviderQueuePolicyV2(
            policy_ref=body.policy_ref,
            provider_id=body.provider_id,
            max_concurrency=body.max_concurrency,
            max_queue_size=body.max_queue_size,
            retry_after_seconds=body.retry_after_seconds,
            allowed_fallback_provider_ids=tuple(body.allowed_fallback_provider_ids),
            max_requests_per_window=body.max_requests_per_window,
            window_seconds=body.window_seconds,
        )
        return config.put("provider_queue", _queue_payload(policy))

    @router.get("/entitlements/{user_id}")
    def get_entitlements(user_id: UUID, request: Request) -> dict[str, Any]:
        _owner_session(app, request)
        return {
            "user_id": str(user_id),
            "capabilities": [item.value for item in entitlements.list_for_user(user_id)],
            "identity_authority": "S2",
        }

    @router.post("/entitlements/{user_id}")
    def set_entitlements(user_id: UUID, body: EntitlementBody, request: Request) -> dict[str, Any]:
        _owner_session(app, request)
        try:
            capabilities = tuple(IntelligenceCapability(item) for item in body.capabilities)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="unknown intelligence capability") from exc
        applied = entitlements.set_for_user(user_id, capabilities, actor_is_owner=True)
        return {
            "user_id": str(user_id),
            "capabilities": [item.value for item in applied],
            "identity_authority": "S2",
        }

    @router.post("/scope-requests/{request_id}/decision")
    def decide_scope_request(request_id: str, body: ScopeDecisionBody, request: Request) -> dict[str, Any]:
        _owner_session(app, request)
        try:
            return config.decide_scope_request(request_id, body.decision)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="scope request unavailable") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    app.include_router(router)
    return app


__all__ = ["DecisionIntelligenceConfigStore", "attach_owner_decision_intelligence"]
