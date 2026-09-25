"""Explicit local-model registry for the AlgoFortis Laya integration."""

from __future__ import annotations

from dataclasses import dataclass
import re


_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_DRIVE_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_URI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


class LayaRegistryError(ValueError):
    """Raised when Laya model registration is unsafe or ambiguous."""


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LayaRegistryError(f"{name} must be a non-empty string")
    return value.strip()


def _relative_local_path(value: object) -> str:
    path = _text(value, "local_path")
    if (
        path.startswith(("/", "\\\\", "//"))
        or _DRIVE_ABSOLUTE_RE.match(path)
        or _URI_RE.match(path)
    ):
        raise LayaRegistryError("local_path must be a relative local path")
    normalized = path.replace("\\", "/")
    parts = tuple(part for part in normalized.split("/") if part not in ("", "."))
    if not parts or ".." in parts:
        raise LayaRegistryError("local_path must be a relative local path")
    return "/".join(parts)


@dataclass(frozen=True, slots=True)
class RegisteredLayaModel:
    model_id: str
    model_version: str
    model_hash: str
    adapter_version: str
    feature_schema_version: str
    local_path: str

    def __post_init__(self) -> None:
        model_id = _text(self.model_id, "model_id")
        model_version = _text(self.model_version, "model_version")
        model_hash = _text(self.model_hash, "model_hash")
        if not _HASH_RE.fullmatch(model_hash):
            raise LayaRegistryError("model_hash must be lowercase 64-character hex")
        adapter_version = _text(self.adapter_version, "adapter_version")
        feature_schema_version = _text(self.feature_schema_version, "feature_schema_version")
        local_path = _relative_local_path(self.local_path)
        object.__setattr__(self, "model_id", model_id)
        object.__setattr__(self, "model_version", model_version)
        object.__setattr__(self, "model_hash", model_hash)
        object.__setattr__(self, "adapter_version", adapter_version)
        object.__setattr__(self, "feature_schema_version", feature_schema_version)
        object.__setattr__(self, "local_path", local_path)

    @property
    def ref(self) -> str:
        return f"{self.model_id}@{self.model_version}"


class LayaModelRegistry:
    """Immutable-in-practice lookup authority for explicitly registered models."""

    def __init__(self, models: tuple[RegisteredLayaModel, ...] | list[RegisteredLayaModel] = ()) -> None:
        if not isinstance(models, (tuple, list)):
            raise LayaRegistryError("models must be a tuple/list")
        by_ref: dict[str, RegisteredLayaModel] = {}
        for model in models:
            if not isinstance(model, RegisteredLayaModel):
                raise LayaRegistryError("models must contain RegisteredLayaModel values")
            if model.ref in by_ref:
                raise LayaRegistryError("duplicate model ref")
            by_ref[model.ref] = model
        self._models = tuple(sorted(by_ref.values(), key=lambda model: model.ref))
        self._by_ref = {model.ref: model for model in self._models}

    def resolve(self, model_ref: str) -> RegisteredLayaModel:
        ref = _text(model_ref, "model_ref")
        try:
            return self._by_ref[ref]
        except KeyError as exc:
            raise LayaRegistryError("model is not registered") from exc

    def list_models(self) -> tuple[RegisteredLayaModel, ...]:
        return self._models


__all__ = ["LayaRegistryError", "RegisteredLayaModel", "LayaModelRegistry"]
