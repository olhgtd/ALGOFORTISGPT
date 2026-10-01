"""Deterministic secret-free G7 evidence markers."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

G7_MARKERS = (
    "APPROVED_ORDER_AUTHORITY=RISK_GATE_V2_ONLY",
    "PORTFOLIO_BUDGETS=VERSIONED_EXPLICIT",
    "CAPITAL_RESERVATION=ATOMIC_FAIL_CLOSED",
    "PORTFOLIO_EXPOSURE=THROUGH_RISK_GATE",
    "CIRCUIT_BREAKER=STICKY_ENTRY_POLICY",
    "EVENT_RISK=SCHEDULED_VERSIONED_NO_SILENT_RESIZE",
    "LIVE_STATE=READ_ONLY/DISARMED",
    "G7_ENABLES_REAL_MONEY_TRADING=NO",
)


@dataclass(frozen=True, slots=True)
class G7Evidence:
    markers: tuple[str, ...]
    fingerprint: str


def build_g7_evidence() -> G7Evidence:
    payload = "\n".join(G7_MARKERS) + "\n"
    return G7Evidence(
        G7_MARKERS,
        sha256(payload.encode("utf-8")).hexdigest(),
    )


def render_g7_evidence() -> str:
    evidence = build_g7_evidence()
    return "\n".join(
        (*evidence.markers, f"FINGERPRINT={evidence.fingerprint}")
    ) + "\n"


__all__ = [
    "G7Evidence",
    "G7_MARKERS",
    "build_g7_evidence",
    "render_g7_evidence",
]
