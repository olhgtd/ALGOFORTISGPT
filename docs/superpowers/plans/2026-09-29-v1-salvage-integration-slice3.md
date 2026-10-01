# V1 Salvage Integration Slice 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve V1 four-broker read-side value—quote normalization, feed compatibility, throttling/reconciliation knowledge—without importing legacy broker mutation authority into current V2 Live/Risk domains.

**Architecture:** Current V2 data/feed contracts remain authoritative. Pure provider-edge quote normalizers are accepted as read-side salvage. Concrete legacy adapters remain compatibility/donor code and must not become direct imports of sensitive V2 Live/Risk modules.

**Tech Stack:** Python, pytest, existing `engine.data.feeds.broker_live_feeds`, static source-boundary tests.

**Spec:** `docs/v1-salvage-reference/PATH_AND_CAPABILITY_MAP.md` on `v1-manual-salvage-reference-20260929`.

## Global Constraints

- Read-side salvage only in this slice.
- No real place/modify/cancel enablement.
- Shared Phase-6 transport runtime owns reconnect/heartbeat/backpressure/subscription replay.
- Pure normalizers may translate broker payloads to canonical `QuoteSnapshot`; they get no execution authority.
- Legacy concrete adapters must not be imported directly by `engine/live` or `engine/risk`.
- Live remains READ_ONLY/DISARMED.

## Review Focus

- Four broker normalizers preserve provider-specific field mapping without fabricating missing prices.
- Naive provider timestamps are localized consistently rather than treated as UTC silently.
- Dhan `LTP` and Angel One best-buy/best-sell/last-traded-price aliases remain supported.
- Sensitive Live/Risk code must not import concrete legacy mutation adapters or factory.
- No new broker credentials/secrets are introduced into data-normalization code.

---

### Task 1: Freeze broker read-side donor map

**Files:**
- Create: `docs/v1-salvage-integration/SLICE3_BROKER_DATA_READ_SIDE.md`

- [ ] Record which V1 capabilities are already represented in current V2.
- [ ] Separate pure read-side salvage from legacy mutation-capable adapters.

### Task 2: Pin four-broker quote normalization

**Files:**
- Create: `tests_v1/test_v1_salvage_broker_read_side_boundaries.py`

- [ ] Test Upstox canonical bid/ask/last/source mapping.
- [ ] Test Zerodha/Kite canonical mapping.
- [ ] Test Dhan `LTP` and timestamp aliases.
- [ ] Test Angel One `best_buy`/`best_sell`/`last_traded_price` aliases.
- [ ] Test absent optional prices stay `None`.

### Task 3: Quarantine concrete legacy mutation adapters

**Files:**
- Extend: `tests_v1/test_v1_salvage_broker_read_side_boundaries.py`

- [ ] Scan `engine/live` and `engine/risk` Python sources.
- [ ] Reject imports of `upstox_adapter`, `kite_adapter`, `dhan_adapter`, `angel_adapter`, or broker-adapter `factory`.
- [ ] Allow canonical contracts/ports required by current V2 architecture.

### Task 4: Verification report

**Files:**
- Create: `docs/v1-salvage-integration/SLICE3_VERIFICATION.md`

- [ ] Record existing V2 feed/transport authorities reused.
- [ ] Record legacy adapter mutation/fallback risk as deliberately not adopted.
- [ ] Record exact runner limitations and leave merge readiness unclaimed until full regression.
