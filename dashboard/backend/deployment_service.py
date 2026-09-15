"""P1-A (R-07): persistent multi-strategy deployment orchestration.

This module manages deployment *state* only. It never executes strategies,
never places orders, and never touches a broker. Execution (where it exists)
stays inside the canonical authorities:

- strategy artifact/version/hash: SQLiteGovernanceStore + verify_artifact
- paper execution: PaperService (simulated only)
- pre-order gating: RiskGate (inside PaperService)
- accounting/orders: VirtualPaperAccount via PaperService

Deployment lifecycle: DEPLOYED <-> PAUSED, * -> STOPPED (terminal),
any -> BLOCKED (Owner/system). STOPPED never reactivates; a new deployment
record is required afterwards.

LIVE execution_mode records may exist but are created BLOCKED and always
re-blocked on resume while live execution is DISARMED. Broker mutation path
remains ZERO; this service has no broker handle by design.
"""

from __future__ import annotations

from typing import Any


class DeploymentError(Exception):
    """Fail-closed deployment orchestration error."""


class DeploymentService:
    """Persistent deployment state orchestration over canonical authorities."""

    def __init__(
        self,
        *,
        security_store,
        governance_store=None,
        artifact_root=None,
        paper_service=None,
    ) -> None:
        if security_store is None:
            raise DeploymentError("Deployment authority requires a security store")
        self._security = security_store
        self._governance = governance_store
        self._artifact_root = artifact_root
        self._paper = paper_service

    # ── helpers ──

    def _resolve_exact_version(self, strategy_id: str, version_id: str | None) -> dict[str, Any]:
        """Resolve the canonical current registered version or fail closed.

        Deployment and strategy-connection mapping share one deliberate version
        contract: both follow the registry's canonical current version. A
        supplied version is an assertion, not independent authority.
        """
        if self._governance is None:
            raise DeploymentError("Governance authority unavailable")
        try:
            conn = self._governance._conn
        except AttributeError as exc:
            raise DeploymentError("Governance authority unavailable") from exc
        registered = self._security.get_owner_strategy(strategy_id)
        if registered is None:
            raise DeploymentError("Strategy is not registered")
        canonical_version_id = str(registered.get("version") or "").strip()
        if not canonical_version_id:
            raise DeploymentError("Canonical strategy version is unavailable")
        if version_id is not None and str(version_id) != canonical_version_id:
            raise DeploymentError("Strategy version does not match the canonical current version")
        rows = conn.execute(
            "SELECT * FROM strategy_versions WHERE strategy_id = ? AND version_id = ?",
            (strategy_id, canonical_version_id),
        ).fetchall()
        if len(rows) != 1:
            raise DeploymentError("Exact registered strategy version required for deployment")
        row = rows[0]
        if row["archived"] or str(row["stage"]).upper() == "ARCHIVED":
            raise DeploymentError("Strategy version is archived")
        registered_author = str(registered.get("author") or "").strip()
        if registered_author and str(row["owner_id"]) != registered_author:
            raise DeploymentError("Strategy version owner does not match strategy authority")
        return {"version_id": row["version_id"], "source_sha256": row["source_sha256"]}

    def _verify_artifact_integrity(self, strategy_id: str, version_id: str) -> dict[str, Any]:
        """Re-verify the exact registered artifact bytes against its sha.

        Fail closed on missing/tampered artifact or hash mismatch. Skipped only
        when no governance/artifact authority is wired (records then carry the
        sha for later verification at execution time inside PaperService).
        """
        if self._governance is None or self._artifact_root is None:
            return {"verified": False, "reason": "ARTIFACT_AUTHORITY_UNAVAILABLE"}
        import hashlib
        from uuid import UUID
        try:
            rows = self._governance._conn.execute(
                "SELECT * FROM strategy_versions WHERE strategy_id = ? AND version_id = ?",
                (strategy_id, version_id)).fetchall()
        except AttributeError as exc:
            raise DeploymentError("Governance authority unavailable") from exc
        if len(rows) != 1:
            raise DeploymentError("Exact registered strategy version required for deployment")
        row = rows[0]
        try:
            path = self._governance.verify_artifact(
                artifact_root=self._artifact_root,
                owner_id=UUID(row["owner_id"]),
                artifact_path=row["artifact_path"],
                digest=row["source_sha256"],
            )
            payload = path.read_bytes()
        except Exception as exc:
            raise DeploymentError("Deployment artifact missing or inaccessible") from exc
        if hashlib.sha256(payload).hexdigest() != row["source_sha256"]:
            raise DeploymentError("Deployment artifact hash mismatch (tampered artifact fails closed)")
        return {"verified": True, "source_sha256": row["source_sha256"]}

    def _connection_readiness(
        self, user_id: str, connection_id: str | None, execution_mode: str,
    ) -> dict[str, Any]:
        try:
            return self._security.check_user_connection_deployment_readiness(
                user_id=user_id,
                connection_id=connection_id,
                execution_mode=execution_mode,
            )
        except Exception as exc:
            raise DeploymentError(str(exc)) from exc

    # ── lifecycle ──

    def create_deployment(
        self,
        *,
        user_id: str,
        strategy_id: str,
        version_id: str | None = None,
        connection_id: str | None = None,
        instrument: str,
        timeframe: str,
        execution_mode: str = "LIVE_PAPER",
        risk_ref: str | None = None,
        actor: str = "USER",
    ) -> dict[str, Any]:
        mode = (execution_mode or "").upper().strip()
        if mode not in {"LIVE_PAPER", "LIVE"}:
            raise DeploymentError(f"Invalid execution mode '{execution_mode}'")
        if mode == "LIVE_PAPER":
            elig_fn = getattr(self._security, "check_self_service_paper_eligibility", None)
            if elig_fn is None:
                raise DeploymentError("Paper eligibility authority unavailable")
            elig = elig_fn(strategy_id, user_id=user_id)
            if not elig.get("permitted"):
                raise DeploymentError(str(elig.get("reason") or "Strategy is not eligible for paper deployment"))
        connection_readiness = self._connection_readiness(user_id, connection_id, mode)
        resolved = self._resolve_exact_version(strategy_id, version_id)
        self._verify_artifact_integrity(strategy_id, resolved["version_id"])

        # A deployment that can become active must have a canonical mapping.
        # Unready connections retain intent as BLOCKED without manufacturing an
        # apparently usable mapping.
        if connection_id is not None and connection_readiness.get("permitted"):
            try:
                self._security.map_strategy_connection(
                    user_id=user_id,
                    strategy_id=strategy_id,
                    connection_id=connection_id,
                    execution_mode=mode,
                    strategy_version_id=resolved["version_id"],
                    governance_store=self._governance,
                    actor=actor,
                )
            except Exception as exc:
                raise DeploymentError(str(exc)) from exc
        try:
            deployment = self._security.create_deployment(
                user_id=user_id,
                strategy_id=strategy_id,
                strategy_version_id=resolved["version_id"],
                source_sha256=resolved["source_sha256"],
                connection_id=connection_id,
                instrument=instrument,
                timeframe=timeframe,
                execution_mode=mode,
                risk_ref=risk_ref,
                actor=actor,
            )
        except Exception as exc:
            raise DeploymentError(str(exc)) from exc
        return deployment

    def get_deployment(self, deployment_id: str, user_id: str | None) -> dict[str, Any]:
        dep = self._security.get_deployment(deployment_id, user_id)
        if dep is None:
            raise DeploymentError("Deployment not found")
        return dep

    def list_deployments(self, user_id: str | None, *, status: str | None = None) -> list[dict[str, Any]]:
        try:
            return self._security.list_deployments(user_id, status=status)
        except Exception as exc:
            raise DeploymentError(str(exc)) from exc

    def pause_deployment(self, deployment_id: str, user_id: str | None, *, actor: str = "USER") -> dict[str, Any]:
        self.get_deployment(deployment_id, user_id)
        try:
            return self._security.transition_deployment(
                deployment_id=deployment_id, user_id=user_id, action="pause", actor=actor)
        except Exception as exc:
            raise DeploymentError(str(exc)) from exc

    def resume_deployment(self, deployment_id: str, user_id: str | None, *, actor: str = "USER") -> dict[str, Any]:
        dep = self.get_deployment(deployment_id, user_id)
        mode = dep.get("executionMode") or dep.get("execution_mode") or "LIVE_PAPER"
        status = str(dep.get("status") or "")
        block_authority = str(dep.get("blockAuthority") or "LEGACY").upper()
        if status == "BLOCKED" and block_authority != "POLICY":
            raise DeploymentError(
                f"{block_authority} blocked deployment cannot be resumed by the user"
            )
        if mode == "LIVE":
            # Fail closed while live execution is DISARMED: record stays BLOCKED.
            # Ownership was verified above; the block itself is a system-safety
            # action, so it runs under system scope.
            try:
                return self._security.transition_deployment(
                    deployment_id=deployment_id, user_id=None, action="block",
                    reason="LIVE_EXECUTION_DISARMED: live real-money execution is disabled in this runtime",
                    actor="SYSTEM", block_authority="SYSTEM")
            except Exception as exc:
                raise DeploymentError(str(exc)) from exc
        # Re-validate before reactivation: strategy eligibility, connection, artifact.
        owner = dep.get("userId") or dep.get("user_id")
        elig_fn = getattr(self._security, "check_self_service_paper_eligibility", None)
        if elig_fn is not None:
            elig = elig_fn(str(dep.get("strategyId") or dep.get("strategy_id")), user_id=owner)
            if not elig.get("permitted"):
                # System-safety block runs under system scope (ownership already verified).
                try:
                    return self._security.transition_deployment(
                        deployment_id=deployment_id, user_id=None, action="block",
                        reason=str(elig.get("reason") or "Strategy no longer eligible"),
                        actor="SYSTEM", block_authority="POLICY")
                except Exception as exc:
                    raise DeploymentError(str(exc)) from exc
        readiness = self._connection_readiness(
            str(owner), dep.get("connectionId") or dep.get("connection_id"), str(mode)
        )
        if not readiness.get("permitted"):
            try:
                return self._security.transition_deployment(
                    deployment_id=deployment_id,
                    user_id=None,
                    action="block",
                    reason=str(readiness.get("reason") or "Connection is not ready"),
                    actor="SYSTEM",
                    block_authority="POLICY",
                )
            except Exception as exc:
                raise DeploymentError(str(exc)) from exc
        self._verify_artifact_integrity(
            str(dep.get("strategyId") or dep.get("strategy_id")),
            str(dep.get("strategyVersionId") or dep.get("strategy_version_id")))
        try:
            return self._security.transition_deployment(
                deployment_id=deployment_id, user_id=user_id, action="resume", actor=actor)
        except Exception as exc:
            raise DeploymentError(str(exc)) from exc

    def stop_deployment(self, deployment_id: str, user_id: str | None, *, actor: str = "USER") -> dict[str, Any]:
        self.get_deployment(deployment_id, user_id)
        try:
            return self._security.transition_deployment(
                deployment_id=deployment_id, user_id=user_id, action="stop", actor=actor)
        except Exception as exc:
            raise DeploymentError(str(exc)) from exc

    def block_deployment(
        self, deployment_id: str, *, reason: str | None = None, actor: str = "OWNER-001",
    ) -> dict[str, Any]:
        self.get_deployment(deployment_id, None)
        try:
            return self._security.transition_deployment(
                deployment_id=deployment_id, user_id=None, action="block",
                reason=reason, actor=actor)
        except Exception as exc:
            raise DeploymentError(str(exc)) from exc

    def link_runtime_session(
        self, deployment_id: str, user_id: str | None, runtime_session_id: str | None,
    ) -> dict[str, Any]:
        """Link a paper session as the deployment's runtime reference.

        Identity is exact, not merely user-scoped. Missing authority or any
        strategy/version/mode/artifact mismatch fails closed.
        """
        dep = self.get_deployment(deployment_id, user_id)
        owner = str(dep.get("userId") or dep.get("user_id"))
        if runtime_session_id is not None:
            if self._paper is None:
                raise DeploymentError("Paper runtime authority unavailable")
            try:
                ses = self._paper.get_session(runtime_session_id, user_id=owner)
            except Exception as exc:
                raise DeploymentError("Runtime session not found for this user") from exc
            if ses is None:
                raise DeploymentError("Runtime session not found for this user")
            deployment_mode = str(dep.get("executionMode") or dep.get("execution_mode") or "").upper()
            session_mode = str(ses.get("data_source_mode") or "").upper()
            if deployment_mode != "LIVE_PAPER" or session_mode != "LIVE_MARKET":
                raise DeploymentError("Runtime session execution mode is incompatible with deployment")
            if str(ses.get("strategy_id") or "") != str(dep.get("strategyId") or dep.get("strategy_id") or ""):
                raise DeploymentError("Runtime session strategy identity does not match deployment")
            if str(ses.get("strategy_version") or "") != str(
                dep.get("strategyVersionId") or dep.get("strategy_version_id") or ""
            ):
                raise DeploymentError("Runtime session version identity does not match deployment")
            if str(ses.get("instrument") or "").upper() != str(dep.get("instrument") or "").upper():
                raise DeploymentError("Runtime session instrument identity does not match deployment")
            if str(ses.get("timeframe") or "") != str(dep.get("timeframe") or ""):
                raise DeploymentError("Runtime session timeframe identity does not match deployment")
            if str(ses.get("status") or "").upper() not in {"INITIALIZED", "ACTIVE"}:
                raise DeploymentError("Runtime session is not linkable in its current state")
            if str(ses.get("owner_allowance") or "ALLOWED").upper() != "ALLOWED":
                raise DeploymentError("Runtime session is not linkable while Owner hold is active")

            strategy_id = str(dep.get("strategyId") or dep.get("strategy_id") or "")
            version_id = str(dep.get("strategyVersionId") or dep.get("strategy_version_id") or "")
            resolved = self._resolve_exact_version(strategy_id, version_id)
            if str(dep.get("sourceSha256") or dep.get("source_sha256") or "") != str(
                resolved.get("source_sha256") or ""
            ):
                raise DeploymentError("Runtime session artifact identity does not match deployment")
            self._verify_artifact_integrity(strategy_id, version_id)
        try:
            return self._security.set_deployment_runtime(
                deployment_id=deployment_id, user_id=user_id, runtime_session_id=runtime_session_id)
        except Exception as exc:
            raise DeploymentError(str(exc)) from exc

    def recovery_snapshot(self, user_id: str | None) -> dict[str, Any]:
        """Restart recovery view: which deployments exist and what they need.

        Never auto-starts execution. DEPLOYED LIVE_PAPER deployments report
        whether their runtime session is still attached/valid.
        """
        deployments = self.list_deployments(user_id)
        items: list[dict[str, Any]] = []
        for dep in deployments:
            needs: list[str] = []
            status = dep.get("status")
            mode = dep.get("executionMode")
            effective_status = status
            effective_block_reason = dep.get("blockReason")
            if status in {"DEPLOYED", "PAUSED"} and mode == "LIVE_PAPER":
                try:
                    readiness = self._connection_readiness(
                        str(dep.get("userId") or dep.get("user_id")),
                        dep.get("connectionId") or dep.get("connection_id"),
                        str(mode),
                    )
                except DeploymentError as exc:
                    readiness = {"permitted": False, "reason": str(exc)}
                if not readiness.get("permitted"):
                    effective_status = "BLOCKED"
                    effective_block_reason = str(readiness.get("reason") or "CONNECTION_NOT_READY")
                    needs.append(effective_block_reason)
            if status == "DEPLOYED" and mode == "LIVE_PAPER" and not dep.get("runtimeSessionId"):
                needs.append("RUNTIME_SESSION_NOT_LINKED")
            if status == "BLOCKED":
                needs.append("BLOCK_REVIEW_REQUIRED")
            if mode == "LIVE":
                effective_status = "BLOCKED"
                effective_block_reason = "LIVE_EXECUTION_DISARMED"
                needs.append("LIVE_EXECUTION_DISARMED")
            items.append({
                "deployment": dep,
                "effectiveStatus": effective_status,
                "effectiveBlockReason": effective_block_reason,
                "needsAttention": needs,
            })
        return {"deployments": items, "count": len(items)}
