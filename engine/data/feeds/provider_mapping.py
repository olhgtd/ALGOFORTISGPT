"""Phase 5 Slice 4C-1 — Generic Provider Instrument Mapping.

Defines provider-neutral transport reference abstractions and mapping boundaries:
- ProviderInstrumentRef (immutable transport identifier)
- ProviderInstrumentMappingError hierarchy
- ProviderInstrumentMapper (runtime-checkable Protocol)
- InMemoryProviderInstrumentMapper (deterministic bidirectional 1-to-1 bijection)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol, Sequence, runtime_checkable

from engine.portfolio.model import InstrumentIdentity

__all__ = [
    "ProviderInstrumentRef",
    "ProviderInstrumentMappingError",
    "UnknownProviderRefError",
    "UnknownInstrumentIdentityError",
    "DuplicateInstrumentMappingError",
    "ProviderInstrumentMapper",
    "InMemoryProviderInstrumentMapper",
]


# ======================================================================
# 1. ProviderInstrumentRef
# ======================================================================


@dataclass(frozen=True)
class ProviderInstrumentRef:
    """Immutable provider-specific transport identifier (Layer 1 transport boundary).

    This represents a broker/feed-level token or symbol reference. It is strictly
    transport metadata and must never replace or contaminate InstrumentIdentity.
    """

    provider: str
    token: str
    exchange: str
    symbol: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("provider must be a non-empty string")
        if not isinstance(self.token, str) or not self.token.strip():
            raise ValueError("token must be a non-empty string")
        if not isinstance(self.exchange, str) or not self.exchange.strip():
            raise ValueError("exchange must be a non-empty string")

        symbol = None
        if self.symbol is not None:
            if not isinstance(self.symbol, str) or not self.symbol.strip():
                raise ValueError("symbol if provided must be a non-empty string")
            symbol = self.symbol.strip()

        object.__setattr__(self, "provider", self.provider.strip().lower())
        object.__setattr__(self, "token", self.token.strip())
        object.__setattr__(self, "exchange", self.exchange.strip().upper())
        object.__setattr__(self, "symbol", symbol)


# ======================================================================
# 2. Mapping Error Hierarchy
# ======================================================================


class ProviderInstrumentMappingError(Exception):
    """Base exception for all provider instrument mapping failures."""


class UnknownProviderRefError(ProviderInstrumentMappingError):
    """Raised when an unknown ProviderInstrumentRef cannot be mapped to InstrumentIdentity."""


class UnknownInstrumentIdentityError(ProviderInstrumentMappingError):
    """Raised when an unknown InstrumentIdentity cannot be mapped to ProviderInstrumentRef."""


class DuplicateInstrumentMappingError(ProviderInstrumentMappingError):
    """Raised when a duplicate or conflicting mapping breaks the strict 1-to-1 bijection."""


# ======================================================================
# 3. ProviderInstrumentMapper Protocol
# ======================================================================


@runtime_checkable
class ProviderInstrumentMapper(Protocol):
    """Provider-neutral bidirectional instrument reference mapper."""

    def to_identity(self, ref: ProviderInstrumentRef) -> InstrumentIdentity:
        """Map provider transport reference to canonical InstrumentIdentity.

        Raises UnknownProviderRefError if unmapped.
        """
        ...

    def to_provider_ref(self, identity: InstrumentIdentity) -> ProviderInstrumentRef:
        """Map canonical InstrumentIdentity to provider transport reference.

        Raises UnknownInstrumentIdentityError if unmapped.
        """
        ...


# ======================================================================
# 4. InMemoryProviderInstrumentMapper
# ======================================================================


class InMemoryProviderInstrumentMapper:
    """Deterministic in-memory bidirectional 1-to-1 instrument mapper.

    Enforces strict bijection:
    - Exactly one InstrumentIdentity per ProviderInstrumentRef.
    - Exactly one ProviderInstrumentRef per InstrumentIdentity.
    - Duplicate exact pairs are accepted idempotently.
    - Any conflicting 1-to-N or N-to-1 mapping fails closed at construction.
    """

    def __init__(
        self,
        mappings: Iterable[tuple[ProviderInstrumentRef, InstrumentIdentity]] | None = None,
    ) -> None:
        ref_to_ident: dict[ProviderInstrumentRef, InstrumentIdentity] = {}
        ident_to_ref: dict[InstrumentIdentity, ProviderInstrumentRef] = {}

        if mappings is not None:
            for pair in mappings:
                if not isinstance(pair, tuple) or len(pair) != 2:
                    raise TypeError("mappings must contain (ProviderInstrumentRef, InstrumentIdentity) tuples")
                ref, ident = pair
                if not isinstance(ref, ProviderInstrumentRef):
                    raise TypeError(f"expected ProviderInstrumentRef, got {type(ref).__name__}")
                if not isinstance(ident, InstrumentIdentity):
                    raise TypeError(f"expected InstrumentIdentity, got {type(ident).__name__}")

                # Check 1-to-1 bijection
                if ref in ref_to_ident and ref_to_ident[ref] != ident:
                    raise DuplicateInstrumentMappingError(
                        f"conflicting identity mapping for provider ref {ref!r}: "
                        f"existing={ref_to_ident[ref]!r} vs new={ident!r}"
                    )
                if ident in ident_to_ref and ident_to_ref[ident] != ref:
                    raise DuplicateInstrumentMappingError(
                        f"conflicting provider ref mapping for identity {ident!r}: "
                        f"existing={ident_to_ref[ident]!r} vs new={ref!r}"
                    )

                ref_to_ident[ref] = ident
                ident_to_ref[ident] = ref

        self._ref_to_ident: dict[ProviderInstrumentRef, InstrumentIdentity] = dict(ref_to_ident)
        self._ident_to_ref: dict[InstrumentIdentity, ProviderInstrumentRef] = dict(ident_to_ref)

        # Deterministic ordered tuples for introspection
        self._ordered_refs: tuple[ProviderInstrumentRef, ...] = tuple(
            sorted(
                self._ref_to_ident.keys(),
                key=lambda r: (r.provider, r.exchange, r.token, r.symbol or ""),
            )
        )
        self._ordered_idents: tuple[InstrumentIdentity, ...] = tuple(
            self._ref_to_ident[r] for r in self._ordered_refs
        )

    def to_identity(self, ref: ProviderInstrumentRef) -> InstrumentIdentity:
        """Map provider reference to canonical InstrumentIdentity."""
        if not isinstance(ref, ProviderInstrumentRef):
            raise TypeError(f"expected ProviderInstrumentRef, got {type(ref).__name__}")
        try:
            return self._ref_to_ident[ref]
        except KeyError as error:
            raise UnknownProviderRefError(f"unmapped provider reference: {ref!r}") from error

    def to_provider_ref(self, identity: InstrumentIdentity) -> ProviderInstrumentRef:
        """Map canonical InstrumentIdentity to provider reference."""
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError(f"expected InstrumentIdentity, got {type(identity).__name__}")
        try:
            return self._ident_to_ref[identity]
        except KeyError as error:
            raise UnknownInstrumentIdentityError(f"unmapped instrument identity: {identity!r}") from error

    def provider_refs(self) -> tuple[ProviderInstrumentRef, ...]:
        """Return deterministic immutable view of all registered provider references."""
        return self._ordered_refs

    def identities(self) -> tuple[InstrumentIdentity, ...]:
        """Return deterministic immutable view of all registered instrument identities."""
        return self._ordered_idents

    def __len__(self) -> int:
        return len(self._ref_to_ident)

    def __contains__(self, item: object) -> bool:
        if isinstance(item, ProviderInstrumentRef):
            return item in self._ref_to_ident
        if isinstance(item, InstrumentIdentity):
            return item in self._ident_to_ref
        return False
