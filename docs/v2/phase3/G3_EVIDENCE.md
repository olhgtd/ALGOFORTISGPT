# AlgoFortis V2 — Phase 3 G3 Evidence

- **Phase:** 3 — Data V2
- **Gate:** G3
- **Status:** PASS at qualification candidate; evidence-head verification required before merge
- **Qualification candidate:** `ef93242ea105400a9342fcb43206bdf5e092fbd8`
- **Qualification workflow:** `V2 Phase 3 Data Verification`
- **Qualification run:** `#92` / `35956239814`
- **Date:** 2026-09-24

## G3 Result

The Phase-3 Data V2 qualification candidate passed the complete dual-Windows verification matrix on both Windows latest and Windows Server 2022 using Python 3.13.14.

### Qualification counts

- Phase-1 focused foundation: **41 passed**
- Phase-2 focused safety spine: **51 passed**
- Phase-3 focused Data V2: **47 passed**
- Full `tests_v1` regression: **349 passed, 1 non-blocking deprecation warning**
- Existing architectural regression certification: **13/13 passed**
- Module-boundary policy: **PASS**
- Compile gate: **PASS**
- Phase-1 static policy: **PASS**
- Phase-2 static policy: **PASS**
- Phase-3 static policy: **PASS**

### Frozen golden fingerprints

- Phase-0 market-data fingerprint: `7620420d3bbe9c3dc805947f86d31e64ec6214f43441edc2844ded1f112e0c35`
- Phase-0 runtime-config fingerprint: `6e9168409c73254f8d38ff92025929ed6ebfa104d5150696fdc75ac03efef616`

Both fingerprints remained unchanged during Phase-3 qualification.

## Phase-3 Evidence Map

### 1. Immutable/versioned historical dataset authority — PASS

`engine/data/catalog.py`, `engine/data/store.py`, and `engine/data/catalog_store.py` provide deterministic dataset/version identities, SHA-256-bound immutable evidence, provenance and lineage, write-once Parquet artifacts, checksum verification, SQLite catalog persistence, and verified backup/restore behavior.

Covered by:
- `tests_v1/test_v2_phase3_dataset_catalog.py`
- `tests_v1/test_v2_phase3_historical_store.py`

### 2. Instrument master, exchange calendar, and as-of rules — PASS

`engine/data/instruments.py` and `engine/data/calendar.py` provide immutable effective-date rules, historical as-of resolution, CE/PE/expiry/strike/lot-size metadata, timezone-aware sessions/holidays, ambiguity rejection, and a future 24x7-calendar seam without implementing crypto in V2.0.

Covered by `tests_v1/test_v2_phase3_instrument_master.py`.

### 3. Deterministic data quality and quarantine — PASS

`engine/data/quality.py` surfaces duplicates, gaps, out-of-order observations, invalid OHLC relationships, negative volume, off-session rows and configured outliers. Invalid source bars are quarantined rather than silently rewritten, and scorecards/fingerprints are deterministic and dataset/version bound.

Covered by `tests_v1/test_v2_phase3_data_quality.py`.

### 4. Deterministic resampling — PASS

`engine/data/resample.py` performs Decimal-preserving, session-anchored integer-minute resampling with deterministic fingerprints, no cross-session leakage, duplicate ambiguity rejection, and fail-closed handling of missing/incomplete inputs.

Covered by `tests_v1/test_v2_phase3_resampling.py`.

### 5. Data licensing policy — PASS

`engine/data/licensing.py` is a pure fail-closed policy gate. Missing/unknown/prohibited acquisition permission is denied; disallowed uses cannot be promoted; synthetic datasets are labelled `SYNTHETIC` and cannot serve as promotion evidence; strict NSE programmatic-acquisition prohibition cannot be overridden by adapter metadata. No downloader or scraper is introduced.

Covered by `tests_v1/test_v2_phase3_data_licensing.py` and the Phase-3 static CI gate.

### 6. Live-feed health and RiskGate entry block — PASS

`engine/data/live_feed.py` and `engine/data/feed_monitor.py` provide broker-neutral live-event health contracts covering exchange/receive timestamps, sequence ordering, staleness, clock skew, market state, disconnect/reconnect and explicit resubscribe recovery. Unsafe or uncertain feed state exposes `entries_allowed=False`, which the existing Phase-2 `RiskGateV2` entry-policy seam rejects before risk evaluation. Protective-exit semantics remain independently allowed.

Covered by `tests_v1/test_v2_phase3_live_feed.py`.

### 7. Phase-3 CI qualification — PASS

`build/tools/check_phase3_data_v2.py` and `.github/workflows/v2-phase0-baseline.yml` enforce Phase-3 authorities/tests on both Windows environments. The static gate requires the Data V2 authorities, forbids network/scraper/concrete-broker imports from the bounded Phase-3 data modules, and locks licensing/feed-safety markers.

Covered by `tests_v1/test_v2_phase3_ci_guard.py` and qualification run #92.

## Safety State

Phase 3 adds data-layer capabilities only. It does **not** enable broker mutation or real-money execution. Existing Phase-2 safety behavior and the project `READ_ONLY` / `DISARMED` posture remain preserved.

## Closure Rule

Per the Phase-3 implementation plan, Phase 3 becomes branch-level complete only after **this evidence commit itself** receives a fresh exact-head dual-Windows GREEN run containing the Phase-3 static/focused gates, full regression, architecture certification and frozen golden fingerprints.
