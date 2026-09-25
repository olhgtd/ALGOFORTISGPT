"""Fail-closed configuration for the AlgoFortis Laya integration."""

from __future__ import annotations

from dataclasses import dataclass

from engine.ai.laya.contracts import LayaRole


@dataclass(frozen=True, slots=True)
class LayaConfig:
    enabled: bool
    enabled_roles: tuple[LayaRole, ...]
    model_ref: str | None
    max_input_age_seconds: int

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be bool")
        if not isinstance(self.enabled_roles, (tuple, list)):
            raise ValueError("enabled_roles must be a tuple/list")
        try:
            roles = tuple(sorted((LayaRole(role) for role in self.enabled_roles), key=lambda role: role.value))
        except (TypeError, ValueError) as exc:
            raise ValueError("enabled_roles contains an unsupported Laya role") from exc
        if len(roles) != len(set(roles)):
            raise ValueError("enabled_roles must not contain duplicates")
        if isinstance(self.max_input_age_seconds, bool) or not isinstance(self.max_input_age_seconds, int):
            raise ValueError("max_input_age_seconds must be an integer")

        model_ref = self.model_ref
        if model_ref is not None:
            if not isinstance(model_ref, str) or not model_ref.strip():
                raise ValueError("model_ref must be a non-empty string when supplied")
            model_ref = model_ref.strip()

        if self.enabled:
            if not roles:
                raise ValueError("enabled Laya requires at least one role")
            if model_ref is None:
                raise ValueError("enabled Laya requires model_ref")
            if self.max_input_age_seconds <= 0:
                raise ValueError("enabled Laya requires positive max_input_age_seconds")
        else:
            if roles or model_ref is not None or self.max_input_age_seconds != 0:
                raise ValueError("disabled Laya configuration must be fully fail-closed")

        object.__setattr__(self, "enabled_roles", roles)
        object.__setattr__(self, "model_ref", model_ref)

    @classmethod
    def disabled(cls) -> "LayaConfig":
        return cls(False, (), None, 0)


__all__ = ["LayaConfig"]
