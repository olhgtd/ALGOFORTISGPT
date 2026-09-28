"""Fail-closed configuration for project-local Laya market intelligence."""

from __future__ import annotations

from dataclasses import dataclass
import re


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_LAYA_MODEL_SHA256 = "891102d372688fc2a094dac56a384bc537b87c63f21f9f3dac0be2b7cbc8d86c"


def _relative_path(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty relative path")
    normalized = value.strip().replace("\\", "/")
    if normalized.startswith(("/", "//")) or ":/" in normalized or ".." in normalized.split("/"):
        raise ValueError(f"{name} must remain inside the AlgoFortis project")
    return normalized


@dataclass(frozen=True, slots=True)
class LayaConfig:
    enabled: bool
    source_dir: str
    model_dir: str
    device: str | None
    max_input_age_seconds: int
    expected_model_sha256: str
    shadow_only: bool = True
    allow_broker_mutation: bool = False
    allow_agent_routing: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be bool")
        object.__setattr__(self, "source_dir", _relative_path(self.source_dir, "source_dir"))
        object.__setattr__(self, "model_dir", _relative_path(self.model_dir, "model_dir"))
        if self.device is not None and (not isinstance(self.device, str) or not self.device.strip()):
            raise ValueError("device must be a non-empty string when supplied")
        if isinstance(self.max_input_age_seconds, bool) or not isinstance(self.max_input_age_seconds, int):
            raise ValueError("max_input_age_seconds must be an integer")
        if self.max_input_age_seconds <= 0:
            raise ValueError("max_input_age_seconds must be positive")
        digest = str(self.expected_model_sha256).lower()
        if not _SHA256_RE.fullmatch(digest):
            raise ValueError("expected_model_sha256 must be lowercase 64-character hex")
        object.__setattr__(self, "expected_model_sha256", digest)

        if self.shadow_only is not True:
            raise ValueError("Laya must remain SHADOW_ONLY in V2.0")
        if self.allow_broker_mutation is not False:
            raise ValueError("Laya broker mutation is prohibited")
        if self.allow_agent_routing is not False:
            raise ValueError("Laya agent routing is prohibited")

    @classmethod
    def local_default(cls) -> "LayaConfig":
        return cls(
            enabled=False,
            source_dir="third_party/laya/upstream",
            model_dir="models/laya/original",
            device="cuda",
            max_input_age_seconds=30,
            expected_model_sha256=DEFAULT_LAYA_MODEL_SHA256,
        )


__all__ = ["DEFAULT_LAYA_MODEL_SHA256", "LayaConfig"]
