"""Project-local Laya runtime using the direct single-model SDK path."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Protocol, runtime_checkable


class LayaUnavailable(RuntimeError):
    """Raised when local Laya inference is unavailable or invalid."""


@runtime_checkable
class LayaRuntime(Protocol):
    def predict(
        self,
        state: Mapping[str, object],
        questions: Mapping[str, object],
    ) -> Mapping[str, object]:
        ...


class DisabledLayaRuntime:
    """Default fail-closed runtime."""

    def predict(
        self,
        state: Mapping[str, object],
        questions: Mapping[str, object],
    ) -> Mapping[str, object]:
        raise LayaUnavailable("Laya is disabled")


class LocalLayaRuntime:
    """Keep one direct Laya checkpoint resident for market-intelligence inference."""

    def __init__(
        self,
        *,
        model_dir: str | Path,
        device: str | None,
        expected_model_sha256: str,
        fast: bool = False,
        compile_model: bool = False,
    ) -> None:
        self._model_dir = Path(model_dir)
        self._device = device
        self._expected_model_sha256 = expected_model_sha256
        self._fast = bool(fast)
        self._compile_model = bool(compile_model)
        self._agent = None

    def _ensure_agent(self):
        if self._agent is not None:
            return self._agent
        model_file = self._model_dir / "model.safetensors"
        if not model_file.is_file():
            raise LayaUnavailable(f"Laya model is missing: {model_file}")
        try:
            import laya
        except Exception as exc:  # pragma: no cover - depends on optional local runtime
            raise LayaUnavailable("Laya Python runtime is not installed") from exc
        try:
            self._agent = laya.load(
                str(self._model_dir),
                device=self._device,
                fast=self._fast,
                compile=self._compile_model,
                expected_sha256={"model.safetensors": self._expected_model_sha256},
            )
        except Exception as exc:  # pragma: no cover - depends on model/runtime/GPU
            raise LayaUnavailable("Laya model failed to load") from exc
        return self._agent

    def predict(
        self,
        state: Mapping[str, object],
        questions: Mapping[str, object],
    ) -> Mapping[str, object]:
        if not isinstance(state, Mapping) or not isinstance(questions, Mapping):
            raise TypeError("state and questions must be mappings")
        agent = self._ensure_agent()
        try:
            result = agent.predict(dict(state), dict(questions))
        except Exception as exc:  # pragma: no cover - runtime dependent
            raise LayaUnavailable("Laya inference failed") from exc
        if not isinstance(result, Mapping):
            raise LayaUnavailable("Laya returned a malformed result")
        return result


__all__ = ["DisabledLayaRuntime", "LayaRuntime", "LayaUnavailable", "LocalLayaRuntime"]
