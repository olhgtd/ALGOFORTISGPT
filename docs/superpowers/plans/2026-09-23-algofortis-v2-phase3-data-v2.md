# AlgoFortis V2 Phase 3 Data V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a trustworthy, immutable, versioned and reproducible local data platform for research and live-feed safety while keeping execution READ_ONLY/DISARMED.

**Architecture:** Add a bounded `engine.data` domain for dataset identity/catalog, historical storage, instrument master, quality, resampling, licensing and live-feed health. Reuse Phase-0/1 deterministic `CanonicalCodec`, Clock/ID primitives, migration/audit foundations and existing market contracts rather than rewriting V1. Historical files are immutable Parquet/Arrow artifacts; operational metadata remains in SQLite; live feed health exposes a narrow entry-policy signal consumed by the Phase-2 Risk Gate.

**Tech Stack:** Python 3.13.14, dataclasses/enums/Decimal, PyArrow 25.0.0, SQLite, pytest 9.1.1, GitHub Actions dual-Windows verification.

**Spec:** `ALGOFORTIS_V2_REQUIREMENTS.md` (DAT-001…008, OPT-001/004), `ALGOFORTIS_V2_IMPLEMENTATION_PLAN.md` Phase 3, `docs/v2/adr/ADR-011-phase3-data-scope-and-storage.md`.

## Global Constraints

- Preserve all Phase-0/1/2 golden and safety behavior; no big-bang V1 rewrite.
- Live remains `READ_ONLY=true`, `DISARMED=true`; Phase 3 introduces zero broker mutation.
- Strict NSE programmatic-acquisition prohibition and dormant-adapter gate remain binding.
- Promotion-eligible options research requires licensed historical option-chain data; synthetic fallback is labelled and excluded from promotion evidence.
- Historical datasets are immutable/versioned and carry checksum, provenance, lineage, licence metadata and quality evidence.
- Historical storage = Parquet/Arrow files queried in-process; operational catalog = SQLite.
- Time comes from injected `Clock`; deterministic identities use `CanonicalCodec`; no direct domain `now()`.
- BTCUSD is deferred to V2.3, but instrument/calendar abstractions must not assume index-options-only semantics.

## Review Focus

1. Dataset immutability: registering the same dataset/version with different bytes or provenance must fail closed.
2. Time/as-of correctness: expiry, lot size, calendar and session rules must resolve using the requested historical date, not today's rules.
3. Data corruption: duplicates/gaps/outliers/bad OHLC relationships must be surfaced deterministically and quarantined where required.
4. Feed uncertainty: stale/sequence-gap/out-of-order/clock-skew/market-halt states must block new entries without disabling protective-exit semantics.
5. Licensing: an adapter with missing/prohibited/ambiguous licence permission must not acquire or promote data.

---

### Task 1: Immutable Dataset Contracts and Catalog

**Files:**
- Create: `engine/data/__init__.py`
- Create: `engine/data/catalog.py`
- Create: `tests_v1/test_v2_phase3_dataset_catalog.py`

**Interfaces:**
- Produces: `DatasetId`, `DatasetVersion`, `DatasetProvenance`, `DatasetRecord`, `DatasetCatalog`, `DatasetCatalogError`.
- Uses: `CanonicalCodec` for deterministic version/checksum-bound identity.

- [ ] RED tests prove deterministic dataset/version IDs, immutable registration, checksum/provenance/lineage/licence fields, duplicate-conflict rejection and deterministic lookup/list ordering.
- [ ] Capture RED because `engine.data.catalog` does not exist.
- [ ] Implement frozen contracts and an in-memory catalog authority with fail-closed validation; no storage I/O yet.
- [ ] Run focused GREEN plus full suite, architecture certification and golden checks.

### Task 2: Parquet Historical Store + SQLite Catalog Persistence

**Files:**
- Create: `engine/data/store.py`
- Create: `engine/data/catalog_store.py`
- Create: `tests_v1/test_v2_phase3_historical_store.py`

**Interfaces:**
- Consumes: `DatasetRecord`, Arrow tables/batches.
- Produces: immutable content-addressed Parquet artifact path, verified checksum, SQLite metadata persistence/restore.

- [ ] RED tests prove write-once artifact semantics, checksum verification on read, atomic temp-to-final publish, corruption detection, operational/historical separation, backup/restore verification and refusal to overwrite an existing dataset version.
- [ ] Implement with PyArrow Parquet and SQLite only; no server process and no network.
- [ ] Verify clean restart can reconstruct catalog metadata and validate stored artifacts.

### Task 3: Instrument Master, Exchange Calendar and As-of Rules

**Files:**
- Create: `engine/data/instruments.py`
- Create: `engine/data/calendar.py`
- Create: `tests_v1/test_v2_phase3_instrument_master.py`

**Interfaces:**
- Produces versioned instrument definitions, CE/PE/expiry/strike/lot-size rules, session/holiday calendar and `as_of` resolution.

- [ ] RED tests cover NIFTY/BANKNIFTY index/options identity, weekly/monthly expiry metadata, symbol normalization, historical lot-size changes, holidays/sessions/timezone normalization and future BTCUSD-compatible 24x7 seam without implementing crypto.
- [ ] Implement immutable effective-date ranges and reject overlapping/ambiguous rules.
- [ ] Verify exact as-of resolution and deterministic fingerprints.

### Task 4: Data Quality Pipeline and Scorecards

**Files:**
- Create: `engine/data/quality.py`
- Create: `tests_v1/test_v2_phase3_data_quality.py`

**Interfaces:**
- Consumes normalized bars/events plus expected calendar/session coverage.
- Produces `QualityIssue`, quarantine decisions, coverage metrics and deterministic `QualityScorecard`.

- [ ] RED tests for duplicates, timestamp gaps, out-of-order input, impossible OHLC, negative volume, configurable outliers, off-session rows and deterministic quality score.
- [ ] Implement pure deterministic validators; quarantine invalid bars instead of silently fixing them.
- [ ] Bind quality score/fingerprint to `DatasetRecord` evidence.

### Task 5: Deterministic Resampling

**Files:**
- Create: `engine/data/resample.py`
- Create: `tests_v1/test_v2_phase3_resampling.py`

**Interfaces:**
- Consumes canonical 1m bars + calendar/session boundaries.
- Produces deterministic higher-timeframe bars and resampling provenance.

- [ ] RED tests cover OHLCV aggregation, exact bucket boundaries, session boundaries, missing-input behavior, no cross-session leakage, timezone normalization and identical result regardless of input ordering.
- [ ] Implement Decimal-preserving deterministic resampling for integer-minute timeframes required by current strategies.
- [ ] Verify fingerprints are identical across repeated/cross-environment runs.

### Task 6: Data Adapter Licensing Gate

**Files:**
- Create: `engine/data/licensing.py`
- Create: `tests_v1/test_v2_phase3_data_licensing.py`
- Extend narrowly: `engine/core/adapter_registry.py` only if required to validate DATA adapter licence metadata.

**Interfaces:**
- Produces explicit acquisition/use permissions and `DataLicenceDecision`.

- [ ] RED tests prove missing/unknown/prohibited acquisition permission fails closed; research-only data cannot be promoted to a disallowed use; synthetic datasets are always labelled; strict NSE programmatic-acquisition prohibition cannot be bypassed by adapter metadata.
- [ ] Implement pure policy evaluation with no downloader/scraper.
- [ ] Verify broker/licensed adapter declarations remain explicit and audited at activation boundaries.

### Task 7: Live Feed Contract, Feed Monitor, Market Status and Entry Block

**Files:**
- Create: `engine/data/live_feed.py`
- Create: `engine/data/feed_monitor.py`
- Create: `tests_v1/test_v2_phase3_live_feed.py`
- Extend narrowly: `engine/risk/gate_v2.py` through the existing entry-policy seam.

**Interfaces:**
- Produces canonical quote/event schema, exchange/receive timestamps, heartbeat, sequence/ordering status, stale/clock-skew status, market-state enum and reconnect/resubscribe state.
- Consumed by `RiskGateV2` as a read-only entry policy; protective exits remain outside the entry block.

- [ ] RED tests cover stale feed, missed sequence, out-of-order event, excessive clock skew, market halt/closed/open transitions, reconnect/resubscribe state and fail-closed uncertainty.
- [ ] RED test proves stale/unsafe feed blocks a new entry through `RiskGateV2` before evaluation while protective-exit semantics are not converted into an entry halt.
- [ ] Implement broker/vendor-neutral monitor with injected Clock and deterministic reason codes; no real data connection required.
- [ ] Verify DAT-005 G3 stale-feed criterion.

### Task 8: Phase 3 CI Qualification and G3 Evidence

**Files:**
- Create: `build/tools/check_phase3_data_v2.py`
- Update: `.github/workflows/v2-phase0-baseline.yml`
- Create: `tests_v1/test_v2_phase3_ci_guard.py`
- Create at qualification: `docs/v2/phase3/G3_EVIDENCE.md`

**Interfaces:**
- Consumes all Phase-3 focused tests plus existing Phase-0/1/2 gates.

- [ ] Add static gate proving required Phase-3 authorities/tests exist, `engine.data` is broker-neutral, no prohibited acquisition/scraper path exists, and historical storage remains local/in-process.
- [ ] Add dedicated Phase-3 focused test step on both Windows environments.
- [ ] Run exact-head dual-Windows qualification: module boundaries, compile, Phase-1/2 gates, Phase-3 static/focused, full regression, 13-test architecture certification and frozen golden fingerprints.
- [ ] Record dataset identity/checksum/provenance/quality evidence, deterministic resampling evidence and stale-feed RiskGate block in `G3_EVIDENCE.md`.
- [ ] Phase 3 is complete only after the evidence commit itself receives a fresh exact-head dual-Windows GREEN run.
