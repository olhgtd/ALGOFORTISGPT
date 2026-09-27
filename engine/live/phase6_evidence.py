"""Deterministic, secret-free G6 qualification evidence."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

G6_EVIDENCE_SCHEMA = "algofortis-g6-readonly-evidence/v2"
_G6_MARKERS = (
    "BROKER_BOUNDARY=V2_ISOLATED_READ_ONLY",
    "BROKER_SCOPE=ANGELONE,ZERODHA,DHAN,UPSTOX",
    "CROSS_BROKER_FAILOVER=DISABLED",
    "FEED_HEALTH_HANDOFF=DATA_V2_FEED_MONITOR",
    "FOREIGN_ACTIVITY_INCIDENT_MODEL=PHASE5_SHARED",
    "G6_ENABLES_REAL_MONEY_TRADING=NO",
    "LIVE_STATE=READ_ONLY/DISARMED",
    "MARKET_DATA_TRANSPORT=SHARED_RUNTIME_THIN_DRIVERS",
    "QUEUE_OVERFLOW=FAIL_CLOSED",
    "REAL_BROKER_MUTATION_CAPABILITY=ABSENT",
    "RECONCILIATION_AUTHORITY=LIVE_RECONCILER",
    "RISK_GATE_FEED_BLOCK=DAT_005_008_EXISTING_PATH",
    "SEQUENCE_KEY=CONNECTION_GENERATION+INSTRUMENT_TOKEN",
    "SOURCE_SEQUENCE=EXPLICIT_SEMANTICS_NO_FABRICATION",
    "STALE_GENERATION=REJECTED",
    "TRANSPORT_HEALTH=LOWER_LEVEL_ONLY",
)


@dataclass(frozen=True, slots=True)
class G6Evidence:
    schema: str
    markers: tuple[str, ...]
    fingerprint: str


def _fingerprint(markers: tuple[str, ...]) -> str:
    payload = (G6_EVIDENCE_SCHEMA + "\n" + "\n".join(markers) + "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_g6_evidence() -> G6Evidence:
    markers = tuple(sorted(_G6_MARKERS))
    return G6Evidence(G6_EVIDENCE_SCHEMA, markers, _fingerprint(markers))


def render_g6_evidence(evidence: G6Evidence) -> str:
    if not isinstance(evidence, G6Evidence):
        raise TypeError("evidence must be G6Evidence")
    lines = [
        f"SCHEMA={evidence.schema}",
        *evidence.markers,
        f"FINGERPRINT={evidence.fingerprint}",
    ]
    return "\n".join(lines) + "\n"


__all__ = [
    "G6_EVIDENCE_SCHEMA",
    "G6Evidence",
    "build_g6_evidence",
    "render_g6_evidence",
]
