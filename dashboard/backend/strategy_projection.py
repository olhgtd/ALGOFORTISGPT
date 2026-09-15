"""DB-004: bounded repair of the operational strategy registry from Governance.

There is no durable 'latest version' in Governance. A write supplies its exact
version; restart uses the registry's valid current reference (the deployment
contract), or the sole non-archived Governance version. Ambiguity fails closed.
"""
from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger(__name__)

# ADDED is registered by StrategyService.submit today. Registration does not
# promote its Governance stage; execution still checks the Governance artifact.
PROJECTABLE_STAGES = ("ADDED", "BACKTEST_ELIGIBLE", "PAPER_ELIGIBLE", "LIVE_ELIGIBLE")
STARTUP_VERSION_LIMIT = 1000


class StrategyProjectionPending(RuntimeError):
    """Governance is retained; the operational projection is not confirmed."""

    def __init__(self, strategy_id=None, version_id=None, *, reason="REGISTRATION_FAILED"):
        self.detail = {
            "code": "STRATEGY_PROJECTION_PENDING",
            "governance_persisted": True,
            "security_projection": "PENDING",
            "strategy_id": str(strategy_id) if strategy_id is not None else None,
            "version_id": str(version_id) if version_id is not None else None,
            "reason": reason,
        }
        super().__init__("Governance persistence succeeded; Security projection is pending")


def projection_evidence(status, strategy_id=None, version_id=None):
    # No exception text, source, filesystem paths, credentials or trading data.
    logger.warning("DB004 %s", {
        "status": status,
        "strategy_id": str(strategy_id) if strategy_id is not None else None,
        "version_id": str(version_id) if version_id is not None else None,
    })


class StrategyProjectionReconciler:
    def __init__(self, *, governance_store, security_store, artifact_root):
        self.governance = governance_store
        self.security = security_store
        self.artifact_root = artifact_root

    def reconcile_version(self, *, strategy_id, version_id) -> bool:
        """One exact post-write repair; never choose a different version."""
        row = self.governance.load_version(version_id)
        if row["strategy_id"] != str(strategy_id):
            raise StrategyProjectionPending(strategy_id, version_id, reason="IDENTITY_CONFLICT")
        if row["archived"] or row["stage"] not in PROJECTABLE_STAGES:
            return False
        if self.security is None:
            raise StrategyProjectionPending(strategy_id, version_id, reason="SECURITY_UNAVAILABLE")
        registered = self.security.get_owner_strategy(str(strategy_id))
        assignment = self.security.get_strategy_assignment(row["owner_id"], str(strategy_id))
        if (registered is not None and registered["version"] == str(version_id)
                and registered["author"] == row["owner_id"] and assignment is not None
                and assignment["version_id"] == str(version_id)):
            return False
        self.governance.verify_artifact(
            artifact_root=self.artifact_root, owner_id=UUID(row["owner_id"]),
            artifact_path=row["artifact_path"], digest=row["source_sha256"],
        )
        self.security.register_backtest_artifact(
            strategy_id=str(strategy_id), version_id=str(version_id),
            name=f"Strategy {str(strategy_id)[:8]}", owner_id=row["owner_id"],
            preserve_assignment_status=True,
        )
        projection_evidence("REPAIRED", strategy_id, version_id)
        return True

    def reconcile_startup(self, *, limit=STARTUP_VERSION_LIMIT) -> int:
        """Bound total work. Any unresolved state prevents dependent startup.

        Ordering is only for reproducible traversal, never version selection.
        No ordinary read endpoint calls this method.
        """
        if self.governance is None:
            return 0
        if not isinstance(limit, int) or not 1 <= limit <= STARTUP_VERSION_LIMIT:
            raise ValueError("invalid strategy reconciliation limit")
        try:
            rows = self.governance._conn.execute(
                "SELECT strategy_id,version_id FROM strategy_versions "
                "WHERE archived=0 AND stage IN (?,?,?,?) "
                "ORDER BY strategy_id,version_id LIMIT ?",
                (*PROJECTABLE_STAGES, limit + 1),
            ).fetchall()
            if len(rows) > limit:
                raise StrategyProjectionPending(reason="STARTUP_LIMIT_EXCEEDED")
            grouped = {}
            for row in rows:
                grouped.setdefault(row["strategy_id"], []).append(row["version_id"])
            repaired = 0
            for strategy_id, versions in grouped.items():
                registered = self.security.get_owner_strategy(strategy_id) if self.security is not None else None
                if registered is not None and registered["version"] in versions:
                    version_id = registered["version"]
                elif len(versions) == 1:
                    version_id = versions[0]
                else:
                    raise StrategyProjectionPending(strategy_id, reason="AMBIGUOUS_CURRENT_VERSION")
                try:
                    repaired += self.reconcile_version(strategy_id=strategy_id, version_id=version_id)
                except StrategyProjectionPending:
                    raise
                except Exception:
                    raise StrategyProjectionPending(strategy_id, version_id) from None
            return repaired
        except StrategyProjectionPending as exc:
            projection_evidence(exc.detail["reason"], exc.detail["strategy_id"], exc.detail["version_id"])
            raise
        except Exception:
            projection_evidence("STARTUP_RECONCILIATION_FAILED")
            raise StrategyProjectionPending(reason="STARTUP_RECONCILIATION_FAILED") from None
