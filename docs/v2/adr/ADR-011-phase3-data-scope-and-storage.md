# ADR-011 — Phase 3 Data Scope, Options Data Policy, and Historical Store

- **Status:** Accepted / FROZEN
- **Date:** 2026-09-23
- **Owner Decisions:** OD-V2-04, OD-V2-10, OD-V2-13
- **Phase:** 3 — Data V2

## Context

Phase 3 cannot start while OD-V2-04, OD-V2-10, or OD-V2-13 is open. The V2 requirements also preserve the existing strict prohibition on unauthorized NSE programmatic acquisition and require every data adapter to declare its licence/terms and permitted use.

## Decision

### OD-V2-04 — Crypto scope

BTCUSD is **deferred to V2.3** behind the same instrument/calendar abstractions. Phase 3 must not hard-code assumptions that prevent a future 24x7 calendar, crypto-specific adapter, fee model, or margin model, but no BTCUSD data adapter or crypto-specific implementation is V2.0 scope.

### OD-V2-10 — Options data source and synthetic policy

Promotion-eligible options research requires **licensed historical option-chain data** whose terms explicitly permit the intended local research/backtest use. Broker-provided history may be used only where the broker's terms explicitly permit the required use and retention.

Synthetic option pricing from underlying data plus an IV/pricing model is allowed only as an explicit fallback for development and exploratory backtests. Synthetic datasets and reports must be labelled `SYNTHETIC`, carry the model/version inputs in provenance, and are **not valid promotion evidence** unless a later dated Owner Decision explicitly changes that rule.

The existing strict NSE programmatic-acquisition prohibition remains binding. Phase 3 does not add a scraper or bypass a source's acquisition/licensing restrictions.

### OD-V2-13 — Historical store technology

V2.0 uses **columnar Parquet/Arrow files + an in-process embedded query/scanning layer + the existing operational SQLite catalog**.

For Phase 3, the in-process query/scanning layer is PyArrow Dataset using the already locked PyArrow runtime dependency. No local database server is introduced. A future internal optimization may add another embedded analytical engine behind the same catalog/store contract, but it may not change dataset identity, checksums, provenance, or immutable-version semantics.

## Consequences

- Historical datasets are immutable/versioned artifacts, not mutable operational tables.
- Every dataset version carries checksum/fingerprint, provenance, coverage, quality score, source/licence metadata, and as-of rules where applicable.
- Storage/query implementation remains local-first and portable; no server process is required.
- Live/order execution remains `READ_ONLY=true` / `DISARMED=true`; this ADR authorizes data-layer work only.
- Phase 3 entry blockers OD-V2-04, OD-V2-10, and OD-V2-13 are FROZEN by this ADR.
