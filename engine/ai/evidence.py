"""Deterministic provenance helpers for AI research/shadow routing and outputs."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class AIEvidenceEnvelope:
    evidence_ref: str
    kind: str
    payload: Mapping[str, Any]


def canonical_evidence(kind: str, payload: Mapping[str, Any]) -> AIEvidenceEnvelope:
    clean_kind = str(kind).strip().upper()
    if not clean_kind:
        raise ValueError("AI evidence kind is required")
    material = {
        "kind": clean_kind,
        "payload": dict(payload),
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return AIEvidenceEnvelope(
        evidence_ref=f"ai-evidence:{digest}",
        kind=clean_kind,
        payload=dict(payload),
    )


def routing_evidence(*, agent_id: str, provider_id: str, model_id: str, scope: str) -> AIEvidenceEnvelope:
    return canonical_evidence(
        "ROUTING",
        {
            "routing_owner": "PRIME",
            "agent_id": agent_id,
            "provider_id": provider_id,
            "model_id": model_id,
            "scope": scope,
            "fallback_mode": "FAIL_CLOSED",
        },
    )
