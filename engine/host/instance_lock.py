"""Single-instance ownership guard for Phase-5 Paper sessions."""

from __future__ import annotations

from typing import Protocol


class InstanceLockBackend(Protocol):
    def try_acquire(self, key: str) -> bool: ...

    def release(self, key: str) -> None: ...


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


class InstanceLock:
    """Fail-closed ownership wrapper around an injected lock backend."""

    def __init__(self, backend: InstanceLockBackend, *, lock_key: str) -> None:
        if backend is None:
            raise TypeError("backend is required")
        self._backend = backend
        self._lock_key = _require_text(lock_key, "lock_key")
        self._acquired = False

    @property
    def acquired(self) -> bool:
        return self._acquired

    def acquire(self) -> bool:
        if self._acquired:
            return True
        acquired = self._backend.try_acquire(self._lock_key)
        if acquired is not True:
            self._acquired = False
            return False
        self._acquired = True
        return True

    def release(self) -> None:
        if not self._acquired:
            return
        self._backend.release(self._lock_key)
        self._acquired = False


__all__ = ["InstanceLock", "InstanceLockBackend"]
