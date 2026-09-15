"""Phase 5 Slice 4C-1 — Operational Live Instrument Catalog.

Provides LiveInstrumentCatalog, an atomic snapshot-driven implementation of the
InstrumentCatalog protocol designed for live and simulated paper trading.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable, Sequence

from engine.options.catalog import InstrumentCatalog, OptionCatalogEntry
from engine.portfolio.model import InstrumentIdentity, InstrumentSpecification

__all__ = [
    "CatalogAmbiguityError",
    "LiveInstrumentCatalog",
]


class CatalogAmbiguityError(ValueError):
    """Raised when incoming catalog entries contain conflicting or ambiguous contracts."""


def _canonical_selection_key(entry: OptionCatalogEntry) -> tuple[str, date | None, Decimal | None, str | None]:
    """Extract canonical option selector lookup key."""
    ident = entry.identity
    return (
        ident.underlying or "",
        ident.expiry,
        ident.strike,
        ident.option_type,
    )


class LiveInstrumentCatalog:
    """Operational snapshot-driven instrument catalog implementing InstrumentCatalog.

    Guarantees:
    - Implements InstrumentCatalog.list_entries(*, underlying, as_of) protocol exactly.
    - Snapshot replacement is completely atomic (all-or-nothing).
    - If any entry is invalid or ambiguous, the existing catalog state is unchanged.
    - list_entries returns immutable tuples in deterministic order.
    - Exposes run-local generation counter incrementing only on successful snapshot replacement.
    """

    def __init__(
        self,
        initial_entries: Iterable[OptionCatalogEntry] | None = None,
    ) -> None:
        self._entries: tuple[OptionCatalogEntry, ...] = ()
        self._generation: int = 0

        if initial_entries is not None:
            self.replace_snapshot(initial_entries)

    @property
    def generation(self) -> int:
        """Return the current snapshot generation counter."""
        return self._generation

    @property
    def all_entries(self) -> tuple[OptionCatalogEntry, ...]:
        """Return an immutable view of all current catalog entries."""
        return self._entries

    def list_entries(
        self,
        *,
        underlying: str,
        as_of: date,
    ) -> tuple[OptionCatalogEntry, ...]:
        """Filter authoritative option entries by underlying and effective date.

        Preserves exact InstrumentCatalog protocol semantics:
        - Case-insensitive underlying matching.
        - Includes entries where specification.effective_from <= as_of.
        - Returns an immutable tuple. Never returns None.
        """
        if not isinstance(underlying, str) or not underlying.strip():
            raise ValueError("underlying must be a non-empty string")
        if not isinstance(as_of, date):
            raise TypeError("as_of must be a date")

        upper = underlying.strip().upper()
        return tuple(
            entry for entry in self._entries
            if entry.identity.underlying == upper
            and entry.specification.effective_from <= as_of
        )

    def replace_snapshot(
        self,
        entries: Iterable[OptionCatalogEntry],
    ) -> None:
        """Atomically replace the current catalog with a new validated snapshot.

        Validation rules:
        1. Every entry must be a valid OptionCatalogEntry.
        2. Disallows ambiguous entries where the same option selection key
           (underlying, expiry, strike, option_type) maps to conflicting
           identities or specifications.
        3. Exact duplicate entries are accepted idempotently.
        4. If any entry fails validation, current state and generation are preserved.
        """
        if entries is None:
            raise TypeError("entries must not be None")

        raw_list = list(entries)
        seen_keys: dict[tuple[str, date | None, Decimal | None, str | None], OptionCatalogEntry] = {}
        validated_unique: list[OptionCatalogEntry] = []

        for entry in raw_list:
            if not isinstance(entry, OptionCatalogEntry):
                raise TypeError(f"expected OptionCatalogEntry, got {type(entry).__name__}")

            key = _canonical_selection_key(entry)
            if key in seen_keys:
                existing = seen_keys[key]
                # Check for conflict in identity or specification
                if existing.identity != entry.identity or existing.specification != entry.specification:
                    raise CatalogAmbiguityError(
                        f"conflicting catalog entry for selection key {key}: "
                        f"existing=(ident={existing.identity!r}, spec={existing.specification!r}) vs "
                        f"new=(ident={entry.identity!r}, spec={entry.specification!r})"
                    )
                # Exact duplicate: accept idempotently, do not duplicate in list
                continue

            seen_keys[key] = entry
            validated_unique.append(entry)

        # Sort deterministically
        sorted_entries = tuple(
            sorted(
                validated_unique,
                key=lambda e: (
                    e.identity.underlying or "",
                    e.identity.expiry or date.min,
                    e.identity.strike or Decimal(0),
                    e.identity.option_type or "",
                    e.identity.instrument,
                ),
            )
        )

        # Atomic replacement
        self._entries = sorted_entries
        self._generation += 1

    def __len__(self) -> int:
        return len(self._entries)
