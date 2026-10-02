"""AlgoFortis V2 — S3 privacy-preserving telemetry and support export.

Operational telemetry is deny-by-default and requires an explicit frozen
TelemetryPrivacyPolicy opt-in. Support bundles are separate explicit user
exports and are sanitized before material is returned.
"""
from __future__ import annotations

import re
import time
from typing import Dict, Any, List, Optional

from dashboard.backend.account_v2.policy_seams import TelemetryPrivacyPolicy

REDACTION_PATTERNS = [
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"(api_key|secret|password|token)\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE), r"\1: '[REDACTED]'"),
    (re.compile(r"C:\\Users\\[^\\]+\\", re.IGNORECASE), lambda m: "C:\\Users\\[REDACTED_USER]\\"),
    (re.compile(r"/home/[^/]+/", re.IGNORECASE), lambda m: "/home/[REDACTED_USER]/"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED_IP]"),
]

HEARTBEAT_DATA_CLASS = "operational_health"


class TelemetryService:
    """Build minimized telemetry only after explicit policy authorization."""

    def __init__(
        self,
        app_version: str = "9.0.0",
        opt_in_crash_reporting: bool = False,
        *,
        privacy_policy: Optional[TelemetryPrivacyPolicy] = None,
    ):
        self.app_version = app_version
        self.opt_in_crash_reporting = opt_in_crash_reporting
        self.privacy_policy = privacy_policy

    def build_operational_heartbeat(self, runtime_state: str, memory_mb: float) -> Dict[str, Any]:
        """Build a minimized heartbeat only when telemetry is explicitly opted in."""
        policy = self.privacy_policy
        if policy is None or not policy.opt_in:
            raise PermissionError("TELEMETRY_OPT_IN_REQUIRED")
        if HEARTBEAT_DATA_CLASS not in policy.allowed_data_classes:
            raise PermissionError("TELEMETRY_DATA_CLASS_NOT_ALLOWED")

        crash_reporting_allowed = (
            self.opt_in_crash_reporting
            and "crash_metadata" in policy.allowed_data_classes
        )
        return {
            "policy_id": policy.policy_id,
            "policy_version": policy.version,
            "app_version": self.app_version,
            "runtime_state": str(runtime_state),
            "memory_usage_mb": round(float(memory_mb), 1),
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "crash_reporting_enabled": crash_reporting_allowed,
        }

    @staticmethod
    def sanitize_string(content: str) -> str:
        clean = content
        for pattern, replacement in REDACTION_PATTERNS:
            clean = pattern.sub(replacement, clean)
        return clean

    def generate_support_bundle(self, raw_logs: List[str], system_info: Dict[str, Any]) -> Dict[str, Any]:
        """Generate redacted diagnostics for an explicit user export action."""
        sanitized_logs = [self.sanitize_string(line) for line in raw_logs]
        sanitized_sys = {
            k: self.sanitize_string(str(v)) if isinstance(v, str) else v
            for k, v in system_info.items()
        }
        return {
            "manifest": {
                "schema": "AlgoFortisSupportBundle/v1",
                "app_version": self.app_version,
                "exported_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "redaction_applied": True,
                "explicit_export_required": True,
            },
            "system_diagnostics": sanitized_sys,
            "sanitized_log_lines": sanitized_logs,
        }
