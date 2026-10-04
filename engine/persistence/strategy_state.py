"""JSON-backed, optimistic-concurrency runtime state persistence."""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import MappingProxyType
from typing import Mapping

from engine.data.feeds.canonical_lock import canonical_target_claim
from engine.data.feeds.path_safety import assert_within_root, path_within_root, require_safe_component
from engine.reproducibility.codec import CanonicalCodec


STATE_DIRECTORY = Path("data/state")
STALE_STATE_WRITE = "STALE_STATE_WRITE"


class _ExpectedAbsent:
    """Explicit creation precondition; absence is never represented by ``None``."""

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only.
        return "EXPECTED_ABSENT"


EXPECTED_ABSENT = _ExpectedAbsent()


class StaleStateWriteError(RuntimeError):
    """A conditional state replacement did not match committed state."""

    code = STALE_STATE_WRITE


@dataclass(frozen=True)
class StateEntry:
    """Immutable loaded state plus its required conditional-save precondition."""

    state: Mapping[str, object]
    expected_prior_fingerprint: str | _ExpectedAbsent

    @property
    def fingerprint(self) -> str | None:
        """The committed entry fingerprint, or ``None`` when the entry is absent."""
        return (
            None
            if self.expected_prior_fingerprint is EXPECTED_ABSENT
            else self.expected_prior_fingerprint
        )


def _state_path(strategy_id: str) -> Path:
    """Return the contained JSON state path for one authoritative strategy ID."""
    safe_strategy_id = require_safe_component(strategy_id, "strategy_id")
    return path_within_root(STATE_DIRECTORY, f"{safe_strategy_id}.json")


def _canonical_state_value(value: object) -> object:
    """Convert JSON-state evidence to an explicitly ordered codec representation."""
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("state mapping keys must be strings")
        return tuple(
            (key, _canonical_state_value(item))
            for key, item in sorted(value.items())
        )
    if isinstance(value, (list, tuple)):
        return tuple(_canonical_state_value(item) for item in value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("state floats must be finite")
        return Decimal(str(value))
    if isinstance(value, (str, int, bool, type(None), Decimal, datetime, date)):
        return value
    raise TypeError(f"state contains unsupported authoritative value: {type(value).__name__}")


def state_entry_fingerprint(state: Mapping[str, object]) -> str:
    """Return the v1 canonical identity for one complete persisted state entry."""
    if not isinstance(state, Mapping):
        raise TypeError("state must be a mapping")
    return CanonicalCodec.fingerprint(
        "algofortis-state-entry/v1",
        (("state", _canonical_state_value(state)),),
    )


def _freeze_state(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_state(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_state(item) for item in value)
    return value


def _thaw_state(value: object) -> object:
    """Return a mutable JSON-compatible copy for the legacy value-only read API."""
    if isinstance(value, Mapping):
        return {key: _thaw_state(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_state(item) for item in value]
    return copy.deepcopy(value)


def _state_entry(state: Mapping[str, object]) -> StateEntry:
    frozen = _freeze_state(copy.deepcopy(dict(state)))
    if not isinstance(frozen, Mapping):  # pragma: no cover - guarded by _freeze_state.
        raise TypeError("state must be a mapping")
    return StateEntry(frozen, state_entry_fingerprint(frozen))


def _read_document(state_path: Path) -> dict[str, dict]:
    """Read only the committed target; malformed committed JSON fails closed."""
    if not state_path.exists():
        return {}
    with state_path.open("r", encoding="utf-8") as state_file:
        document = json.load(state_file)
    if not isinstance(document, dict) or not all(
        isinstance(version, str) and isinstance(state, dict)
        for version, state in document.items()
    ):
        raise ValueError("committed strategy state document has invalid shape")
    return document


def _write_document(state_path: Path, document: Mapping[str, dict]) -> None:
    """Atomically publish a complete state document or retain the prior commit."""
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=state_path.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            assert_within_root(temporary_path, STATE_DIRECTORY)
            json.dump(document, temporary_file, allow_nan=False, sort_keys=True, separators=(",", ":"))
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        assert_within_root(temporary_path, STATE_DIRECTORY)
        temporary_path.replace(state_path)
    except BaseException:
        if temporary_path is not None and temporary_path.exists():
            assert_within_root(temporary_path, STATE_DIRECTORY)
            temporary_path.unlink()
        raise


def load_state_entry(strategy_id: str, interface_version: str, strategy) -> StateEntry:
    """Load immutable state and the exact token required for a future save."""
    state_path = _state_path(strategy_id)
    document = _read_document(state_path)
    if interface_version not in document:
        initial_state = strategy.initial_state()
        if not isinstance(initial_state, dict):
            raise TypeError("strategy.initial_state() must return a dict")
        return StateEntry(_freeze_state(copy.deepcopy(initial_state)), EXPECTED_ABSENT)
    return _state_entry(document[interface_version])


def load_state(strategy_id: str, interface_version: str, strategy) -> dict:
    """Legacy value-only Rule 2 read wrapper; writes remain conditional."""
    state = _thaw_state(load_state_entry(strategy_id, interface_version, strategy).state)
    if not isinstance(state, dict):  # pragma: no cover - StateEntry guarantees a mapping.
        raise TypeError("loaded state must be a dict")
    return state


def save_state(
    strategy_id: str,
    interface_version: str,
    state: dict,
    *,
    expected_prior_fingerprint: str | _ExpectedAbsent,
) -> None:
    """Conditionally persist one state entry without losing other versions."""
    if not isinstance(interface_version, str) or not interface_version:
        raise ValueError("interface_version must be a non-empty string")
    if not isinstance(state, dict):
        raise TypeError("state must be a dict")
    if expected_prior_fingerprint is not EXPECTED_ABSENT and not (
        isinstance(expected_prior_fingerprint, str) and expected_prior_fingerprint
    ):
        raise TypeError("expected_prior_fingerprint must be a fingerprint or EXPECTED_ABSENT")

    state_path = _state_path(strategy_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    # Freeze the caller's mutable replacement before validating its identity.
    replacement = copy.deepcopy(state)
    state_entry_fingerprint(replacement)

    with canonical_target_claim(state_path, STATE_DIRECTORY):
        document = _read_document(state_path)
        current = document.get(interface_version)
        current_token: str | _ExpectedAbsent = (
            EXPECTED_ABSENT if current is None else state_entry_fingerprint(current)
        )
        if current_token != expected_prior_fingerprint:
            raise StaleStateWriteError(STALE_STATE_WRITE)

        document[interface_version] = replacement
        _write_document(state_path, document)
