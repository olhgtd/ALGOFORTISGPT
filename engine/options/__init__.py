# flake8: noqa: F401
"""Pure option contract selection — Slice A.

Converts a semantic entry intent plus authoritative option catalog
evidence into a deterministic concrete option contract selection.

This module produces NO executable orders, NO risk sizing, and NO
broker submissions.  It only resolves which option contract to trade.

Frozen semantics:
  - SignalIntent BUY  -> select CE
  - SignalIntent SELL -> select PE
  - SignalIntent HOLD -> no selection (returns rejection)
  - SignalIntent EXIT -> selector bypass (returns rejection)

The original SignalIntent is NEVER mutated.
"""

from engine.options.catalog import (
    InstrumentCatalog,
    InMemoryInstrumentCatalog,
    OptionCatalogEntry,
)
from engine.options.policy import (
    ExpiryPolicy,
    OptionSelectionPolicy,
    StrikeMode,
    StrikePolicy,
)
from engine.options.selector import (
    OptionSelector,
    OptionSelectionEvidence,
    OptionSelectionRejection,
    ResolvedOptionEntry,
)

__all__ = [
    # Catalog
    "InstrumentCatalog",
    "InMemoryInstrumentCatalog",
    "OptionCatalogEntry",
    # Policy
    "ExpiryPolicy",
    "OptionSelectionPolicy",
    "StrikeMode",
    "StrikePolicy",
    # Selector
    "OptionSelector",
    "OptionSelectionEvidence",
    "OptionSelectionRejection",
    "ResolvedOptionEntry",
]
