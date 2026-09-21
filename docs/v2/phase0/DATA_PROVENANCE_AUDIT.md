# AlgoFortis V2 — Phase 0 Data Provenance Audit

**Status:** AUDITED — V1 foundation frozen; V2 catalog gap recorded  
**Date:** 2026-09-21

## Scope

This audit asks what the current V1 repository can prove about historical data integrity and provenance before V2 Data work begins. It does not invent or certify datasets that are not present in the repository.

## Current V1 strengths

### Exact approved-file loading

`dashboard/backend/backtest_datasets.py::ApprovedDatasetFiles`:

- resolves datasets only beneath the approved root;
- reads the exact file bytes;
- computes SHA-256 on those bytes;
- rejects a dataset when the supplied `hashSha256` does not match;
- decodes the same bytes after hashing, preventing silent file replacement between hash and load.

This is a strong immutable-input foundation for a run that already has an approved dataset record.

### Historical data inventory and integrity

`dashboard/backend/historical_data_service.py` maintains `DatasetInventoryItem` records containing:

- instrument;
- timeframe;
- start/end dates;
- row count and trading-day coverage;
- `file_sha256`;
- logical path;
- gap status;
- update timestamp and completeness state.

The service re-hashes cached parquet files, re-indexes stale/missing metadata, validates OHLCV, normalizes timestamps and manages gap analysis. The service describes SHA-256 fingerprinting as authoritative for its local cache.

### Provider and fail-closed behavior

Historical providers expose configured/enabled state and supported instruments/timeframes. Unsupported external-provider configuration fails closed instead of fabricating synthetic market data. Synthetic automated-test data is explicitly identified as synthetic/test provider data.

### Reproducibility identity

`engine/reproducibility/market_data.py` builds canonical `MarketDataStream` and `MarketDataSnapshot` fingerprints from normalized instrument identity, policy and Decimal-converted OHLCV bars. `engine/reproducibility/source.py` and dependency/runtime identities provide complementary code/runtime evidence.

## Repository data availability

The repository's `data/` hierarchy contains structure/placeholders rather than a committed production historical-data corpus. Therefore Phase 0 cannot truthfully make a dataset-by-dataset claim about years of NIFTY/BANKNIFTY coverage from GitHub contents alone.

This is not treated as a source-code defect: production datasets are expected to remain local rather than be committed into the source repository.

## V2 gaps confirmed

The current V1 foundation does **not yet provide the complete V2 dataset catalog contract** required by AF2-DAT-001/008. In particular, a universal immutable catalog entry is not proven to carry all of:

- stable dataset ID + immutable dataset version;
- source/provider provenance bound to the dataset version;
- lineage / parent-transform identity;
- licence/terms and permitted-use metadata;
- quality-score identity;
- explicit publication/freeze state.

`file_sha256` and coverage metadata are valuable foundations, but they do not by themselves equal the V2 catalog/provenance/licensing contract.

## Phase 0 ruling

1. Preserve the existing exact-hash loader, inventory SHA-256 and canonical market-data fingerprint behavior.
2. Do not rewrite V1 historical-data storage during Phase 0.
3. Record the full dataset catalog/licensing/provenance contract as **V1→V2 gap G-006**, to be implemented in Phase 3.
4. G0 may close when the absence of a committed production dataset is explicitly documented and all Phase-0 gate evidence is satisfied; G0 does **not** certify data coverage that cannot be observed from the repository.
5. Any future dataset used for promotion evidence must enter the V2 catalog with immutable version/checksum/provenance/licence evidence before G3 can pass.

## Safety / compliance note

The existing dormant/acquisition gates and fail-closed external-provider behavior remain frozen. V2 must not bypass provider licence/ToS restrictions merely to fill a historical-data gap.
