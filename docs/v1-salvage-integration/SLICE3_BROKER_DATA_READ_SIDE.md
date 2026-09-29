# Slice 3 — Broker/Data Read-Side Salvage

## Purpose

Carry forward the manually-built V1 broker/data value that is useful to current AlgoFortis without adopting the legacy mutation-capable broker adapters as V2 Live execution authority.

## Current V2 representation found

The integration tree already contains pure provider-edge quote normalizers in:

`engine/data/feeds/broker_live_feeds.py`

Covered providers:

- Upstox;
- Zerodha/Kite;
- Dhan;
- Angel One.

These normalizers translate provider payload fields into canonical `QuoteSnapshot` values and do not own order execution.

The file explicitly documents the current Phase-6 boundary:

- pure normalizers own payload translation only;
- shared `engine.data.transports` runtime owns reconnect/heartbeat/generation fencing/backpressure/subscription replay;
- legacy feed wrappers remain compatibility seams, not the new transport authority.

## V1 capabilities considered already carried forward

### Quote normalization

Current V2 has explicit four-provider canonical normalizers, including provider aliases:

- Upstox: `bid`, `ask`, `last_price`;
- Kite: `bid`, `ask`, `last_price`;
- Dhan: `LTP` fallback to `last_price`, `time`/`timestamp`;
- Angel One: `best_buy`, `best_sell`, `last_traded_price` fallbacks.

### Feed/reconnect semantics

Legacy reconnect/backoff wrappers still exist for compatibility, but the Phase-6 shared transport runtime is the authority. V1 reconnect behavior is therefore donor/reference knowledge only where it does not conflict with the shared transport contract.

### Rate-limit / auth / reconciliation patterns

The legacy concrete broker adapters still contain useful historical handling for:

- 401/403 authentication errors;
- HTTP 429 normalization;
- server/network failure normalization;
- order/funds/position/reconciliation shapes.

These are **reference/test donors**. They are not automatically promoted into the V2 execution path.

## Safety finding: legacy concrete adapters are mutation-capable

The old concrete adapters under `engine/broker_adapters/` include place/modify/cancel capabilities. For example the Upstox adapter advertises mutation capabilities and contains an internal mock-success transport fallback when no HTTP transport is supplied.

That behavior is acceptable only as historical/offline compatibility code. It must **not** become evidence that real Live execution is enabled and must not be imported directly into sensitive V2 Live/Risk authorities.

## Slice-3 regression boundary

Added:

`tests_v1/test_v1_salvage_broker_read_side_boundaries.py`

It pins:

- four-broker canonical price/source mapping;
- Dhan/Angel provider field aliases;
- India-localization for naive exchange timestamps;
- no fabrication of absent bid/ask/last prices;
- no direct import of concrete legacy adapters/factory by `engine/live` or `engine/risk`.

## What is deliberately not adopted

- legacy `submit()` as V2 authority;
- legacy `cancel()` as V2 authority;
- legacy `modify()` as V2 authority;
- mock-success mutation fallback;
- adapter-local in-memory order store as production truth;
- any interpretation of broker connection as Live armed.

## Permanent destination rule

Use V1 broker work as:

- pure parsing/normalization knowledge;
- error-mapping knowledge;
- catalog/token/reconciliation test cases;
- read-side compatibility evidence.

Current V2 broker contract, RiskGateV2, Live state machine and explicit execution gating remain authoritative.
