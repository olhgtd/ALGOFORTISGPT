"""AlgoFortis privacy-preserving telemetry and explicit support export.

OD-V2-22:
- telemetry is opt-in and policy allowlisted;
- no policy means no telemetry emission;
- support bundles are explicit user exports and are always sanitized.
"""
from __future__ import annotations

import re
import time
from typing import Any

from dashboard.backend.account_v2.policy_seams import TelemetryPrivacyPolicy

REDACTION_PATTERNS = [
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"(api_key|secret|password|token)\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE), r"\1: '[REDACTED]'"),
    (re.compile(r"C:\\Users\\[^\\]+\\", re.IGNORECASE), lambda m: "C:\\Users\\[REDACTED_USER]\\"),
    (re.compile(r"/home/[^/]+/", re.IGNORECASE), lambda m: "/home/[REDACTED_USER]/"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED_IP]"),
]


class TelemetryService:
    """Emits only policy-authorized coarse operational telemetry."""

    def __init__(
        self,
        app_version: str = "9.0.0",
        opt_in_crash_reporting: bool = False,
        *,
        privacy_policy: TelemetryPrivacyPolicy | None = None,
    ):
        self.app_version = app_version
        self.opt_in_crash_reporting = opt_in_crash_reporting
        self.privacy_policy = privacy_policy

    def build_operational_heartbeat(
        self,
        runtime_state: str,
        memory_mb: float,
    ) -> dict[str, Any] | None:
        """Build an allowlisted heartbeat only after explicit opt-in."""
        policy = self.privacy_policy
        if (
            policy is None
            or not policy.opt_in
            or "operational_health" not in policy.allowed_data_classes
        ):
            return None
        return {
            "app_version": self.app_version,
            "runtime_state": runtime_state,
            "memory_usage_mb": round(memory_mb, 1),
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "crash_reporting_enabled": self.opt_in_crash_reporting,
            "telemetry_policy_id": policy.policy_id,
            "telemetry_policy_version": policy.version,
        }

    @staticmethod
    def sanitize_string(content: str) -> str:
        clean = content
        for pattern, replacement in REDACTION_PATTERNS:
            clean = pattern.sub(replacement, clean)
        return clean

    def generate_support_bundle(
        self,
        raw_logs: list[str],
        system_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate a redacted bundle only when the caller explicitly invokes export."""
        sanitized_logs = [self.sanitize_string(line) for line in raw_logs]
        sanitized_sys = {
            key: self.sanitize_string(str(value)) if isinstance(value, str) else value
            for key, value in system_info.items()
        }
        return {
            "manifest": {
                "schema": "AlgoFortisSupportBundle/v1",
                "app_version": self.app_version,
                "exported_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "redaction_applied": True,
            },
            "system_diagnostics": sanitized_sys,
            "sanitized_log_lines": sanitized_logs,
        }
