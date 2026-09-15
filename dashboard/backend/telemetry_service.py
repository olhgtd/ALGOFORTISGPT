"""AlgoFortis V1 — Privacy-Preserving Telemetry & Support Bundle Sanitizer
Implements ADR-22.
- Core Rule: TRADING DATA STAYS LOCAL UNLESS EXPLICITLY EXPORTED.
- Allowed Telemetry: App version, crash signatures, runtime compatibility, update state.
- Prohibited Telemetry: Broker keys, strategies, code, orders, trades, positions, P&L, datasets.
- Support Bundle: Redacts sensitive paths, usernames, IPs, and tokens before generation.
"""
import re
import json
import time
from typing import Dict, Any, List, Optional, Set

# Regex patterns for redaction
REDACTION_PATTERNS = [
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"(api_key|secret|password|token)\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE), r"\1: '[REDACTED]'"),
    (re.compile(r"C:\\Users\\[^\\]+\\", re.IGNORECASE), lambda m: "C:\\Users\\[REDACTED_USER]\\"),
    (re.compile(r"/home/[^/]+/", re.IGNORECASE), lambda m: "/home/[REDACTED_USER]/"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED_IP]"),
]


class TelemetryService:
    """Collects coarse operational metrics and builds privacy-compliant support bundles."""

    def __init__(self, app_version: str = "9.0.0", opt_in_crash_reporting: bool = False):
        self.app_version = app_version
        self.opt_in_crash_reporting = opt_in_crash_reporting

    def build_operational_heartbeat(self, runtime_state: str, memory_mb: float) -> Dict[str, Any]:
        """Build anonymized operational heartbeat."""
        return {
            "app_version": self.app_version,
            "runtime_state": runtime_state,
            "memory_usage_mb": round(memory_mb, 1),
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "crash_reporting_enabled": self.opt_in_crash_reporting
        }

    @staticmethod
    def sanitize_string(content: str) -> str:
        """Apply redaction filters to clean logs and text payloads."""
        clean = content
        for pattern, replacement in REDACTION_PATTERNS:
            clean = pattern.sub(replacement, clean)
        return clean

    def generate_support_bundle(self, raw_logs: List[str], system_info: Dict[str, Any]) -> Dict[str, Any]:
        """Generate redacted, previewable support diagnostic bundle for explicit user export."""
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
                "redaction_applied": True
            },
            "system_diagnostics": sanitized_sys,
            "sanitized_log_lines": sanitized_logs
        }
