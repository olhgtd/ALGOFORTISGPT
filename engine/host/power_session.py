"""Temporary sleep-prevention and resume classification boundary."""

from __future__ import annotations

from typing import Protocol

from engine.paper.contracts_v2 import PaperOperationalState


class PowerSessionBackend(Protocol):
    def request_sleep_prevention(self) -> None: ...

    def release_sleep_prevention(self) -> None: ...

    def resume_detected(self) -> bool: ...


class PowerSessionProvider:
    """Uses only temporary session-scoped power requests through an adapter."""

    def __init__(self, backend: PowerSessionBackend) -> None:
        if backend is None:
            raise TypeError("backend is required")
        self._backend = backend
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def begin_session(self) -> None:
        if self._active:
            return
        self._backend.request_sleep_prevention()
        self._active = True

    def end_session(self) -> None:
        if not self._active:
            return
        self._backend.release_sleep_prevention()
        self._active = False

    def resume_detected(self) -> bool:
        detected = self._backend.resume_detected()
        if not isinstance(detected, bool):
            raise TypeError("resume_detected backend result must be bool")
        return detected


def classify_power_event(provider: PowerSessionProvider) -> PaperOperationalState:
    if not isinstance(provider, PowerSessionProvider):
        raise TypeError("provider must be PowerSessionProvider")
    if provider.resume_detected():
        return PaperOperationalState.RECOVERY
    return PaperOperationalState.HEALTHY


__all__ = ["PowerSessionBackend", "PowerSessionProvider", "classify_power_event"]
