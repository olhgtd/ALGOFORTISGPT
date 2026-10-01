# Slice 3 Verification — Broker/Data Read-Side Salvage

## Status

**Implementation status:** READ-SIDE GUARDS ADDED / FULL-REPO-UNVERIFIED

Slice 3 deliberately adds no broker mutation implementation. It freezes provider normalization behavior and the boundary that keeps legacy concrete mutation-capable adapters out of sensitive V2 Live/Risk modules.

## Changed in Slice 3

Added:

- `tests_v1/test_v1_salvage_broker_read_side_boundaries.py`
- `docs/v1-salvage-integration/SLICE3_BROKER_DATA_READ_SIDE.md`
- `docs/superpowers/plans/2026-09-29-v1-salvage-integration-slice3.md`

Runtime files modified by Slice 3: **none**.

## Existing V2 capability reused

`engine/data/feeds/broker_live_feeds.py` already contains pure normalizers for:

- Upstox;
- Zerodha/Kite;
- Dhan;
- Angel One.

The current file also explicitly assigns real reconnect/heartbeat/backpressure/subscription replay authority to the shared Phase-6 transport runtime rather than the legacy wrapper.

## Safety finding recorded

Legacy files under `engine/broker_adapters/` are mutation-capable compatibility code. The Upstox legacy adapter, for example, advertises PLACE/MODIFY/CANCEL capability and contains a mock-success fallback if no transport client is present.

Slice 3 does **not** adopt this as V2 Live authority. The new static test rejects direct imports of these concrete legacy adapters/factory by `engine/live` and `engine/risk`.

## New test coverage pending execution

The Slice-3 test file pins:

- Upstox bid/ask/last/source normalization;
- Kite bid/ask/last/source normalization;
- Dhan `LTP` alias + IST handling;
- Angel One best-buy/best-sell/last-traded-price aliases + IST handling;
- missing optional prices remain `None`;
- concrete legacy broker adapters stay out of sensitive Live/Risk source trees.

## Verification limitation

The new test file has been committed but **has not been executed by a repository runner in this session**. Therefore:

- Slice-3 focused pytest: **PENDING RUNNER VERIFICATION**;
- full Python regression: **PENDING**;
- Windows hosted qualification: **PENDING**;
- merge readiness: **NOT CLAIMED**.

## Safety posture

No change in this slice enables:

- real broker place/modify/cancel;
- Live arming;
- broker-secret centralization;
- direct AI/Laya broker access;
- a second RiskGate or broker authority.

Current V2 contracts remain authoritative.
