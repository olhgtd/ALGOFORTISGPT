"""Narrow application services that adapt dashboard actions to engine authorities."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol
from uuid import UUID, uuid4

from .domain import StrategyStage, UserIdentity
from .strategy_validation import StaticValidationResult, StrategyValidationError, validate_static_python
from .governance_store import SQLiteGovernanceStore, GovernanceStoreError
from .strategy_projection import (
    PROJECTABLE_STAGES, StrategyProjectionPending, StrategyProjectionReconciler,
    projection_evidence,
)


class DashboardAudit(Protocol):
    def record(self, *, actor_id: UUID, action: str, payload: dict[str, object]) -> None: ...


class StrategyConformanceAuthority(Protocol):
    """Existing trusted conformance/sandbox authority; never the dashboard."""
    def validate_version(self, version: "StrategyVersion") -> bool: ...


class PromotionEvidenceAuthority(Protocol):
    """Existing backtest/paper evidence authority; dashboard may only query it."""
    def permits_promotion(self, version: "StrategyVersion", target: StrategyStage) -> bool: ...


class BacktestAuthority(Protocol):
    """Existing SentinelX backtest application seam, not dashboard code."""
    def run_strategy_version(self, version: "StrategyVersion") -> object: ...


class NullAudit:
    def record(self, *, actor_id: UUID, action: str, payload: dict[str, object]) -> None:
        return None


@dataclass(frozen=True)
class StrategyVersion:
    strategy_id: UUID
    version_id: UUID
    owner_id: UUID
    source_sha256: str
    source_artifact: str
    stage: StrategyStage
    archived: bool = False
    protective_policy_identity: str | None = None


class StrategyService:
    """Strategy metadata authority only; it never executes submitted source."""
    def __init__(
        self,
        *,
        artifact_root: Path,
        audit: DashboardAudit | None = None,
        conformance_authority: StrategyConformanceAuthority | None = None,
        promotion_evidence_authority: PromotionEvidenceAuthority | None = None,
        backtest_authority: BacktestAuthority | None = None,
        governance_store: SQLiteGovernanceStore | None = None,
        security_store: object | None = None,
    ) -> None:
        self._artifact_root = artifact_root
        self._audit = audit or NullAudit()
        self._versions: dict[UUID, StrategyVersion] = {}
        self._conformance_authority = conformance_authority
        self._promotion_evidence_authority = promotion_evidence_authority
        self._backtest_authority = backtest_authority
        self._governance_store = governance_store
        self._security_store = security_store
        self._projection = StrategyProjectionReconciler(
            governance_store=governance_store, security_store=security_store,
            artifact_root=artifact_root,
        )

    def submit(
        self,
        *,
        owner: UserIdentity,
        source: str,
        protective_policy_identity: str | None,
        validate_conformance: bool = False,
    ) -> tuple[StrategyVersion | None, StaticValidationResult]:
        result = validate_static_python(source)
        if not result.accepted:
            self._audit.record(actor_id=owner.user_id, action="STRATEGY_STATIC_VALIDATION_REJECTED", payload={"reasons": list(result.reasons)})
            return None, result
        if validate_conformance:
            from dashboard.backend.strategy_execution import validate_bounded_strategy_source
            ok, reason = validate_bounded_strategy_source(source)
            if not ok:
                conformance_res = StaticValidationResult(False, (f"BoundedStrategy conformance failed: {reason}",))
                self._audit.record(actor_id=owner.user_id, action="STRATEGY_CONFORMANCE_REJECTED", payload={"reasons": list(conformance_res.reasons)})
                return None, conformance_res
        strategy_id, version_id = uuid4(), uuid4()
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        artifact = self._artifact_root / f"usr_{owner.user_id}" / "strategies" / str(strategy_id) / f"{version_id}.py"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        staging = artifact.with_suffix(".staging")
        staging.write_bytes(source.encode("utf-8"))
        os.replace(staging, artifact)
        version = StrategyVersion(strategy_id, version_id, owner.user_id, digest, str(artifact), StrategyStage.ADDED, protective_policy_identity=protective_policy_identity)
        self._versions[version_id] = version
        self._persist(version)
        self._audit.record(actor_id=owner.user_id, action="STRATEGY_SUBMITTED", payload={"strategy_id": str(strategy_id), "version_id": str(version_id), "source_sha256": digest})
        return version, result

    def mark_validated(self, *, actor: UserIdentity, version_id: UUID) -> StrategyVersion:
        version = self._owned(actor, version_id)
        if self._conformance_authority is None:
            raise StrategyValidationError("trusted strategy conformance authority is unavailable")
        try:
            conformance_valid = self._conformance_authority.validate_version(version)
        except Exception as exc:
            raise StrategyValidationError("strategy conformance authority failed closed") from exc
        if conformance_valid is not True:
            raise StrategyValidationError("strategy contract conformance failed")
        if version.archived:
            raise StrategyValidationError("archived strategy cannot be validated")
        updated = StrategyVersion(**{**version.__dict__, "stage": StrategyStage.BACKTEST_ELIGIBLE})
        self._versions[version_id] = updated
        self._persist(updated)
        self._audit.record(actor_id=actor.user_id, action="STRATEGY_BACKTEST_ELIGIBLE", payload={"version_id": str(version_id)})
        return updated

    def run_backtest(self, *, actor: UserIdentity, version_id: UUID) -> object:
        version = self._owned(actor, version_id)
        if version.stage is not StrategyStage.BACKTEST_ELIGIBLE:
            raise StrategyValidationError("strategy is not BACKTEST_ELIGIBLE")
        if self._backtest_authority is None:
            raise StrategyValidationError("authoritative backtest service is unavailable")
        try:
            result = self._backtest_authority.run_strategy_version(version)
        except Exception as exc:
            raise StrategyValidationError("authoritative backtest failed closed") from exc
        if result is None:
            raise StrategyValidationError("authoritative backtest returned no evidence")
        self._audit.record(actor_id=actor.user_id, action="STRATEGY_BACKTEST_REQUESTED", payload={"version_id": str(version_id)})
        return result

    def promote(self, *, actor: UserIdentity, version_id: UUID, target: StrategyStage) -> StrategyVersion:
        version = self._owned(actor, version_id)
        allowed = {
            (StrategyStage.BACKTEST_ELIGIBLE, StrategyStage.PAPER_ELIGIBLE),
            (StrategyStage.PAPER_ELIGIBLE, StrategyStage.LIVE_ELIGIBLE),
        }
        if (version.stage, target) not in allowed:
            raise StrategyValidationError("invalid strategy eligibility promotion")
        if target is StrategyStage.PAPER_ELIGIBLE and not version.protective_policy_identity:
            raise StrategyValidationError("strategy protective policy is NOT_YET_DEFINED")
        if self._promotion_evidence_authority is None:
            raise StrategyValidationError("authoritative promotion evidence is unavailable")
        try:
            permitted = self._promotion_evidence_authority.permits_promotion(version, target)
        except Exception as exc:
            raise StrategyValidationError("authoritative promotion evidence failed closed") from exc
        if permitted is not True:
            raise StrategyValidationError("authoritative promotion evidence does not permit promotion")
        updated = StrategyVersion(**{**version.__dict__, "stage": target})
        self._versions[version_id] = updated
        self._persist(updated)
        self._audit.record(actor_id=actor.user_id, action="STRATEGY_PROMOTED", payload={"version_id": str(version_id), "target": target.value})
        return updated

    def archive(self, *, actor: UserIdentity, version_id: UUID) -> StrategyVersion:
        version = self._owned(actor, version_id)
        updated = StrategyVersion(**{**version.__dict__, "stage": StrategyStage.ARCHIVED, "archived": True})
        self._versions[version_id] = updated
        self._persist(updated)
        self._audit.record(actor_id=actor.user_id, action="STRATEGY_ARCHIVED", payload={"version_id": str(version_id)})
        return updated

    def _owned(self, actor: UserIdentity, version_id: UUID) -> StrategyVersion:
        try: version = self._versions[version_id]
        except KeyError:
            if self._governance_store is None: raise StrategyValidationError("unknown strategy version")
            try:
                row=self._governance_store.load_version(version_id)
                artifact=self._governance_store.verify_artifact(artifact_root=self._artifact_root, owner_id=UUID(row["owner_id"]), artifact_path=row["artifact_path"], digest=row["source_sha256"])
                version=StrategyVersion(UUID(row["strategy_id"]), UUID(row["version_id"]), UUID(row["owner_id"]), row["source_sha256"], str(artifact), StrategyStage(row["stage"]), bool(row["archived"]), row["protective_policy_identity"])
                self._versions[version_id]=version
            except (GovernanceStoreError, ValueError) as exc: raise StrategyValidationError("durable strategy metadata unavailable") from exc
        if actor.user_id != version.owner_id and actor.role.value != "OWNER":
            raise PermissionError("cross-user strategy access denied")
        return version

    def _persist(self, version: StrategyVersion) -> None:
        if self._governance_store is not None:
            self._governance_store.save_version({"strategy_id":str(version.strategy_id),"version_id":str(version.version_id),"owner_id":str(version.owner_id),"source_sha256":version.source_sha256,"artifact_path":version.source_artifact,"stage":version.stage.value,"archived":int(version.archived),"protective_policy_identity":version.protective_policy_identity,"created_at_utc":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()})
        # Archival must not recreate a missing operational registration.
        if version.archived or version.stage.value not in PROJECTABLE_STAGES:
            return
        if self._governance_store is None and self._security_store is None:
            return  # Existing explicitly in-memory service mode.
        try:
            self._security_store.register_backtest_artifact(
                strategy_id=str(version.strategy_id), version_id=str(version.version_id),
                name=f"Strategy {str(version.strategy_id)[:8]}", owner_id=str(version.owner_id),
            )
        except Exception:
            projection_evidence("IMMEDIATE_REPAIR_REQUIRED", version.strategy_id, version.version_id)
            if self._governance_store is None:
                raise  # No committed Governance record exists to reconcile.
            try:
                self._projection.reconcile_version(
                    strategy_id=version.strategy_id, version_id=version.version_id,
                )
            except Exception:
                projection_evidence("PENDING", version.strategy_id, version.version_id)
                raise StrategyProjectionPending(version.strategy_id, version.version_id) from None

    def list_user_strategies(self, user_id: UUID, role: object) -> list[dict[str, object]]:
        """List strategies accessible to a user from persistent governance/security store (F-10)."""
        uid = str(user_id)
        is_owner = getattr(role, "value", str(role)) == "OWNER"
        results: list[dict[str, object]] = []

        gov_versions: list[dict[str, object]] = []
        if self._governance_store is not None:
            try:
                if is_owner:
                    with self._governance_store._tx() as cur:
                        rows = cur.execute("SELECT * FROM strategy_versions ORDER BY created_at_utc DESC").fetchall()
                        gov_versions = [dict(r) for r in rows]
                else:
                    rows = self._governance_store.versions_for(user_id)
                    gov_versions = [dict(r) for r in rows]
            except Exception:
                gov_versions = []

        assigned_strat_ids: set[str] = set()
        strat_gov: dict[str, dict[str, object]] = {}
        global_strat_ids: set[str] = set()
        if self._security_store is not None:
            try:
                if hasattr(self._security_store, "list_user_strategy_assignments") and not is_owner:
                    assignments = self._security_store.list_user_strategy_assignments(uid)
                    for asgn in assignments:
                        assigned_strat_ids.add(str(asgn["strategy_id"]))
                if hasattr(self._security_store, "list_owner_strategies"):
                    owner_strats = self._security_store.list_owner_strategies()
                    for s in owner_strats:
                        s_id = str(s.get("strategyId") or s.get("strategy_id") or "")
                        if s_id:
                            strat_gov[s_id] = s
                            # Explicit global catalog is discoverable by normal
                            # users; private rows of others stay excluded.
                            if not is_owner and (s.get("visibility") or "OWNER_PRIVATE") == "GLOBAL":
                                global_strat_ids.add(s_id)
            except Exception:
                pass

        seen_keys: set[tuple[str, str]] = set()

        for v in gov_versions:
            s_id = str(v["strategy_id"])
            v_id = str(v["version_id"])
            key = (s_id, v_id)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            gov_rec = strat_gov.get(s_id, {})
            admin_status = gov_rec.get("adminStatus") or gov_rec.get("admin_status") or "ACTIVE"
            effective_stage = v.get("stage", "ADDED")
            if admin_status != "ACTIVE":
                effective_stage = f"SUSPENDED_{admin_status}"

            results.append({
                "strategy_id": s_id,
                "version_id": v_id,
                "stage": effective_stage,
                "archived": bool(v.get("archived", False)),
                "source_sha256": v.get("source_sha256", ""),
                "protective_policy": v.get("protective_policy_identity") or "NOT_YET_DEFINED",
                "admin_status": admin_status,
                "visibility": str(gov_rec.get("visibility") or "PRIVATE"),
            })

        # Assigned + explicit-global strategies resolve to the exact persisted
        # governance rows (strategy_id/version_id/sha), never synthesized.
        for asgn_id in assigned_strat_ids | global_strat_ids:
            gov_rec = strat_gov.get(asgn_id, {})
            if not gov_rec:
                continue
            # F-10 exact identity: assigned strategies resolve to the exact
            # persisted governance rows (strategy_id/version_id/sha), never
            # synthesized identifiers.
            exact_rows: list[dict[str, object]] = []
            if self._governance_store is not None:
                try:
                    with self._governance_store._tx() as cur:
                        fetched = cur.execute(
                            "SELECT * FROM strategy_versions WHERE strategy_id = ? ORDER BY created_at_utc DESC",
                            (asgn_id,),
                        ).fetchall()
                        exact_rows = [dict(r) for r in fetched]
                except Exception:
                    exact_rows = []
            if not exact_rows:
                continue
            for v in exact_rows:
                s_id = str(v["strategy_id"])
                v_id = str(v["version_id"])
                key = (s_id, v_id)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                admin_status = gov_rec.get("adminStatus") or gov_rec.get("admin_status") or "ACTIVE"
                effective_stage = str(v.get("stage", "ADDED"))
                if admin_status != "ACTIVE":
                    effective_stage = f"SUSPENDED_{admin_status}"
                results.append({
                    "strategy_id": s_id,
                    "version_id": v_id,
                    "stage": effective_stage,
                    "archived": bool(v.get("archived", False)),
                    "source_sha256": v.get("source_sha256", ""),
                    "protective_policy": v.get("protective_policy_identity") or "NOT_YET_DEFINED",
                    "admin_status": admin_status,
                    "visibility": str(gov_rec.get("visibility") or "PRIVATE"),
                })

        for vid, version in self._versions.items():
            s_id = str(version.strategy_id)
            v_id = str(version.version_id)
            key = (s_id, v_id)
            if key not in seen_keys:
                if user_id == version.owner_id or is_owner or s_id in assigned_strat_ids:
                    seen_keys.add(key)
                    gov_rec = strat_gov.get(s_id, {})
                    admin_status = gov_rec.get("adminStatus") or gov_rec.get("admin_status") or "ACTIVE"
                    effective_stage = version.stage.value
                    if admin_status != "ACTIVE":
                        effective_stage = f"SUSPENDED_{admin_status}"
                    results.append({
                        "strategy_id": s_id,
                        "version_id": v_id,
                        "stage": effective_stage,
                        "archived": version.archived,
                        "source_sha256": version.source_sha256,
                        "protective_policy": version.protective_policy_identity or "NOT_YET_DEFINED",
                        "admin_status": admin_status,
                        "visibility": str(gov_rec.get("visibility") or "PRIVATE"),
                    })

        for s_id, s_data in strat_gov.items():
            author = str(s_data.get("author") or "")
            if is_owner or author == uid or s_id in assigned_strat_ids or s_id in global_strat_ids:
                if not any(r["strategy_id"] == s_id for r in results):
                    results.append({
                        "strategy_id": s_id,
                        "version_id": str(s_data.get("version") or s_data.get("activeVersion") or s_data.get("version_id") or "v1.0.0"),
                        "stage": str(s_data.get("stage") or "ADDED"),
                        "archived": False,
                        "source_sha256": str(s_data.get("source_sha256") or ""),
                        "protective_policy": str(s_data.get("protectivePolicy") or s_data.get("protective_policy_identity") or "NOT_YET_DEFINED"),
                        "admin_status": str(s_data.get("adminStatus") or s_data.get("admin_status") or "ACTIVE"),
                        "visibility": str(s_data.get("visibility") or "PRIVATE"),
                    })

        return results


class DashboardSafeMode:
    """Dashboard-local mutation gate; it cannot alter engine safety state."""
    def __init__(self) -> None:
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def require_mutable(self) -> None:
        if self._enabled:
            raise PermissionError("dashboard SAFE MODE blocks mutable dashboard actions")
