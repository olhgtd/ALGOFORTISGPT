"""Deterministic Phase-5 recovery and G5 evidence helpers."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from engine.paper.contracts_v2 import RecoveryReport
from engine.persistence.paper_codec_v2 import dumps_record

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _hex(value: object, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"{field} has invalid fingerprint format")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _text_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{field} must be a tuple")
    return tuple(_text(item, field) for item in value)


class EvidenceWriter:
    @staticmethod
    def recovery_fingerprint(report: RecoveryReport) -> str:
        if not isinstance(report, RecoveryReport):
            raise TypeError("report must be RecoveryReport")
        payload = dumps_record(report).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def build_g5_manifest(
        *,
        commit_sha: str,
        config_fingerprint: str,
        data_fingerprint: str,
        fault_profile_ref: str,
        recovery_fingerprints: tuple[str, ...],
        failure_injection_refs: tuple[str, ...],
        drift_report_ref: str | None,
        alert_evidence_refs: tuple[str, ...],
        host_evidence_refs: tuple[str, ...],
        soak_started: bool,
    ) -> dict[str, Any]:
        commit_sha = _hex(commit_sha, "commit_sha", _HEX40)
        config_fingerprint = _hex(config_fingerprint, "config_fingerprint", _HEX64)
        data_fingerprint = _hex(data_fingerprint, "data_fingerprint", _HEX64)
        fault_profile_ref = _text(fault_profile_ref, "fault_profile_ref")
        recovery_fingerprints = tuple(
            _hex(item, "recovery_fingerprint", _HEX64) for item in recovery_fingerprints
        )
        failure_injection_refs = _text_tuple(failure_injection_refs, "failure_injection_refs")
        alert_evidence_refs = _text_tuple(alert_evidence_refs, "alert_evidence_refs")
        host_evidence_refs = _text_tuple(host_evidence_refs, "host_evidence_refs")
        if drift_report_ref is not None:
            drift_report_ref = _text(drift_report_ref, "drift_report_ref")
        if not isinstance(soak_started, bool):
            raise TypeError("soak_started must be bool")

        blockers: list[str] = []
        if not recovery_fingerprints:
            blockers.append("MISSING_RECOVERY_EVIDENCE")
        if not failure_injection_refs:
            blockers.append("MISSING_FAILURE_INJECTION_EVIDENCE")
        if drift_report_ref is None:
            blockers.append("MISSING_DRIFT_EVIDENCE")
        if not alert_evidence_refs:
            blockers.append("MISSING_ALERT_EVIDENCE")
        if not host_evidence_refs:
            blockers.append("MISSING_HOST_EVIDENCE")
        if not soak_started:
            blockers.append("SOAK_NOT_STARTED")

        manifest: dict[str, Any] = {
            "schema": "algofortis.phase5.g5-evidence/v1",
            "commit_sha": commit_sha,
            "config_fingerprint": config_fingerprint,
            "data_fingerprint": data_fingerprint,
            "fault_profile_ref": fault_profile_ref,
            "recovery_fingerprints": list(sorted(recovery_fingerprints)),
            "failure_injection_refs": list(sorted(failure_injection_refs)),
            "drift_report_ref": drift_report_ref,
            "alert_evidence_refs": list(sorted(alert_evidence_refs)),
            "host_evidence_refs": list(sorted(host_evidence_refs)),
            "soak_started": soak_started,
            "g5_eligible": not blockers,
            "blockers": blockers,
        }
        canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        manifest["manifest_fingerprint"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return manifest


__all__ = ["EvidenceWriter"]
