"""Broker-independent instrument catalog boundary for option selection.

The selector may select ONLY an authoritative catalog entry.
It MUST NOT synthesize: symbol, expiry, strike, option_type, lot size,
multiplier, minimum quantity, quantity step, price increment, or exchange token.

Every selectable entry carries authoritative InstrumentIdentity and
InstrumentSpecification.  specification.identity must exactly equal selected identity.

For Slice A tests/replay, use deterministic InMemoryInstrumentCatalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

from engine.portfolio.model import InstrumentIdentity, InstrumentSpecification


@dataclass(frozen=True)
class OptionCatalogEntry:
    """One authoritative catalog entry for a single option contract.

    The selector consumes these entries; it never synthesizes any field.
    """

    identity: InstrumentIdentity
    specification: InstrumentSpecification

    def __post_init__(self) -> None:
        if not isinstance(self.identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        if not isinstance(self.specification, InstrumentSpecification):
            raise TypeError("specification must be an InstrumentSpecification")
        # Identity/specification must match exactly
        if self.specification.identity != self.identity:
            raise ValueError(
                "specification.identity must exactly equal the entry's identity; "
                f"got spec.identity={self.specification.identity!r} vs entry.identity={self.identity!r}"
            )
        # Options segment required
        if self.identity.segment != "options":
            raise ValueError("catalog entries must have segment='options'")


@runtime_checkable
class InstrumentCatalog(Protocol):
    """Broker-independent boundary for available option contracts.

    Implementations provide authoritative option chain data from whatever
    source is appropriate (exchange API, static test fixture, file, etc.).

    The protocol is intentionally minimal — the selector only needs to query
    by underlying and optionally filter by expiry/option_type/strike range.
    """

    def list_entries(
        self,
        *,
        underlying: str,
        as_of: date,
    ) -> tuple[OptionCatalogEntry, ...]:
        """Return all authoritative option entries for one underlying.

        The returned entries are frozen and carry full identity + specification.
        Only entries whose effective_from <= as_of are included (no future-effective
        specifications).

        Returns empty tuple if no entries match.  Never returns None.
        """
        ...


class InMemoryInstrumentCatalog:
    """Deterministic in-memory catalog for Slice A testing and replay.

    Accepts a pre-built tuple of OptionCatalogEntry values at construction.
    All queries filter from this frozen set — no external calls, no network,
    no filesystem access.
    """

    def __init__(self, entries: tuple[OptionCatalogEntry, ...]) -> None:
        if not isinstance(entries, tuple):
            raise TypeError("entries must be a tuple of OptionCatalogEntry")
        if not all(isinstance(e, OptionCatalogEntry) for e in entries):
            raise TypeError("every entry must be an OptionCatalogEntry")
        object.__setattr__(self, "_entries", entries)

    def list_entries(
        self,
        *,
        underlying: str,
        as_of: date,
    ) -> tuple[OptionCatalogEntry, ...]:
        """Filter entries by underlying (case-insensitive) and effective date."""
        if not isinstance(underlying, str) or not underlying.strip():
            raise ValueError("underlying must be a non-empty string")
        if not isinstance(as_of, date):
            raise TypeError("as_of must be a date")

        upper = underlying.upper()
        return tuple(
            e for e in self._entries
            if e.identity.underlying == upper
            and e.specification.effective_from <= as_of
        )

    @property
    def all_entries(self) -> tuple[OptionCatalogEntry, ...]:
        """Read-only view of all entries (for inspection/testing)."""
        return self._entries
