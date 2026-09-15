# SentinelX — Project Structure

**Purpose:** Physical folder/module layout. Maps every class/contract defined in `architecture-rules.md` to an actual file location, so no developer or AI agent has to guess where new code belongs.
**Depends on:** `architecture-rules.md` (Rules 1–8), `CLAUDE.md` (build order).
**Rule:** If a new file doesn't fit an existing folder below, that's a signal to stop and ask before inventing a new one — don't let structure drift silently.

> Structural relocation note: modules listed below reflect the FINAL physical paths after
> the approved structure-only migration (M1–M10). Contracts and semantics were unchanged;
> only import paths moved. Historical path references inside frozen records
> (`BACKTEST_ENGINE_ARCHITECTURE_DECISIONS.md`, `SENTINELX_PROGRESS.md`) are retained as
> historical evidence and are not rewritten.

```
sentinelx/
├── import_data.py                 # manual historical-data importer command
├── architecture-rules.md
├── requirements-freeze-125.md
├── PROJECT_STRUCTURE.md
├── CONFIG_SCHEMA.md
├── backlog.md
│
├── config/
│   ├── strategies/                 # one YAML per strategy, per CONFIG_SCHEMA.md
│   │   └── observational_default.yaml
│   ├── risk_config.yaml            # per-trade risk %, max daily loss %, etc. (Q55-63)
│   ├── execution_config.yaml       # order type, slippage/brokerage profiles (Q23-27)
│   ├── logging_config.yaml         # build-order Phase 6 Logging/Audit sink config (§123.6)
│   └── broker_profiles/            # broker profile YAMLs (Phase 7 target)
│
├── data/                           # repository-root dataset area — NOT relocated by the migration
│   ├── raw/                        # untouched source dumps
│   ├── incoming/                   # manually dropped historical-data files awaiting importer processing
│   ├── parquet/                    # ingested, de-duped, validated (Q6-12)
│   ├── quarantine/                 # unresolved importer inputs; never silently stored as production data
│   ├── import_reports/             # per-source importer manifests and quarantine reports
│   └── snapshots/                  # dataset hash manifests (Phase 4.5)
│
├── engine/
│   ├── core/
│   │   └── numeric.py              # shared Decimal helpers (as_decimal etc.)
│   ├── data/                       # data domain package (M10 relocation; contracts unchanged)
│   │   ├── access.py               # get_data() wrapper (Rule 5) — the ONLY strategy-facing entry point
│   │   └── feeds/                  # feed/ingestion/importer package relocated INTACT from engine/feeds/
│   │       ├── base.py             # DataFeed ABC — .fetch() (Rule 4)
│   │       ├── historical_feed.py  # HistoricalDataFeed
│   │       ├── live_feed.py        # LiveMarketDataFeed (Phase 7)
│   │       ├── replay_feed.py      # HistoricalReplayFeed
│   │       ├── ingestion.py        # raw OHLCV ingestion into validated Parquet (Phase 1)
│   │       ├── gap_handler.py      # missing-candle filling + eligibility flags (Phase 1)
│   │       ├── rollover.py         # futures-rollover configuration validation (Phase 1)
│   │       ├── data_cleaning.py    # timestamp normalization / OHLCV validation helpers (Phase 1)
│   │       ├── canonical_lock.py   # canonical-target claim locking
│   │       ├── path_safety.py      # path containment guards
│   │       ├── provider_mapping.py # provider stream mapping
│   │       ├── quote_cache.py      # LatestQuoteCache
│   │       ├── subscription.py     # OptionSubscriptionManager
│   │       ├── live_bar_builder.py # live provider-bar construction
│   │       ├── importer_*.py       # Phase 1 importer foundation (discovery/identity/detection/storage/reporting/orchestrator)
│   │       └── upstox/             # provider-specific Upstox live-feed adapter (auth/catalog/decoder/dispatcher/feed/normalizer/proto)
│   ├── strategy/
│   │   ├── base.py                 # StrategySignalGenerator ABC, Signal class (Rule 1)
│   │   └── exceptions.py           # safe_generate_signal() wrapper (Rule 7)
│   ├── audit/                      # audit domain package (M7 relocation; contracts unchanged)
│   │   ├── model.py                # versioned AuditEvent envelope, D16 taxonomy, event IDs (former engine/audit.py)
│   │   ├── log.py                  # narrow Rule 7 audit-record facade (former engine/audit_log.py)
│   │   └── sinks.py                # Q88/Q89/Q90 structured file-sink infrastructure (former engine/logging_sinks.py)
│   ├── safety/                     # safety domain package (M9 relocation; contracts unchanged)
│   │   ├── safety.py               # SafetyState/KillSwitchState/SafetyManager (intact rename; finer split DEFERRED)
│   │   ├── phase8_safety.py        # Phase8SafetyController + escalation arithmetic (intact rename; finer split DEFERRED)
│   │   ├── alerts.py              # operator-facing safety-alert routing/sinks (former engine/phase8_alerts.py)
│   │   └── strategy_halt.py        # Rule 7 strategy-halt facade
│   ├── risk/
│   │   └── risk_manager.py         # RiskPolicy + Q64 sizing + pre-order RiskGate (Phase 3)
│   ├── protective/                 # protective domain package (M6 relocation; contracts unchanged)
│   │   ├── runtime.py              # protective exits runtime book (former engine/protective.py)
│   │   ├── plan.py                 # strategy-owned pre-entry protective plans (former engine/protective_plan.py)
│   │   └── live.py                 # live protective application (former engine/protective_live.py)
│   ├── orders/, execution/         # broker-agnostic order interface — build-order Phase 4 (VERIFIED_COMPLETE)
│   ├── orchestration/              # orchestration domain package (M4 relocation; contracts unchanged)
│   │   ├── entry_pipeline.py       # deterministic entry pipeline (former engine/orchestration.py)
│   │   ├── signal_intake.py        # SignalIntake / SignalIntent
│   │   └── strategy_coordinator.py # LiveStrategyCoordinator — RUNTIME strategy-entry gating authority (_halted_owners)
│   ├── paper/                      # paper trading domain package (M5 relocation; contracts unchanged)
│   │   ├── runner.py               # backtest paper runner (former engine/paper_runner.py)
│   │   ├── live_runner.py          # live paper trading runner
│   │   ├── coordinator.py          # LivePaperCoordinator incl. global kill-switch authority
│   │   ├── configuration.py        # paper configuration loading/promotion verification
│   │   ├── option_bridge.py        # OptionEntryBridge
│   │   └── promotion_tracking.py   # upstream promotion evidence tracking
│   ├── reconciliation/             # reconciliation domain package (M8 relocation; contracts unchanged)
│   │   └── paper/
│   │       └── engine.py           # PaperReconciliationEngine (former engine/reconciliation.py); broker_contract/ realization DEFERRED
│   ├── persistence/
│   │   ├── sqlite_store.py         # SQLitePaperStateStore — durable audit journal authority (§123.5)
│   │   ├── strategy_state.py       # per-strategy JSON state persistence (former engine/state_store.py)
│   │   └── schema.py
│   ├── portfolio/                  # account snapshots, positions, virtual account, accounting
│   ├── market/                     # MarketDataCoordinator, StreamKey, session profiles (provider-independent)
│   ├── options/                    # option catalog/policy/selector
│   ├── costs/                      # cost model/calculator/projection
│   ├── trades/                     # trade ledger models
│   ├── reporting/                  # Q92/Q93 report models/writers
│   ├── reproducibility/            # CanonicalCodec, manifests, replay support
│   ├── backtest/                   # backtest domain package (M1 relocation; contracts unchanged)
│   │   ├── engine.py               # next-bar-open execution, cost simulator (Phase 3)
│   │   ├── historical_run.py
│   │   ├── validation.py           # walk-forward, bootstrap CI, Monte Carlo (Q30-35)
│   │   ├── walk_forward.py
│   │   ├── metrics.py              # the 15 standard metrics (Phase 4)
│   │   ├── regime.py
│   │   └── finalization.py
│   └── broker_adapters/
│       └── contracts.py, mock_broker.py, mock_pipeline.py, mock_recovery.py, normalization.py
│                                   # zerodha_adapter.py plugs in last, Phase 7 — not built yet
│
├── strategies/
│   └── orb/
│       └── orb_strategy.py         # StrategySignalGenerator subclass
│
├── logs/                           # build-order Phase 6 — approved scope (§123), nothing created yet
│   ├── trade_log/                  # Q88 trade log — not built yet
│   ├── error_log/                  # Q89 error log — not built yet
│   ├── strategy_log/               # Q90 per-strategy evaluation log — not built yet
│   └── audit_log/                  # derived, regenerable, NON-authoritative export of SQLite audit_events — export tooling not built yet
│
├── reports/
│   └── backtest_runs/              # one folder per run: config snapshot + data hash + results (Phase 4.5)
│
├── dashboard/                      # build-order Phase 9 — dashboard/control surface: PLANNED (NOT BUILT); FastAPI backend + React/TypeScript/Vite frontend per ADR §131 (supersedes earlier "Phase 10 / Streamlit" naming)
│
└── tests/                          # full regression suite (2,554 tests)
    ├── test_data_access.py
    ├── test_backtest_engine.py
    ├── test_state_store.py
    └── (per-domain regression suites; ORB conformance coverage included)
```

## Phase 1 ingestion module

`engine/data/feeds/ingestion.py` — raw OHLCV ingestion into validated Parquet files.

## Phase 1 gap handler

`engine/data/feeds/gap_handler.py` — missing-candle filling with gap and signal-eligibility flags.

## Phase 1 rollover module

`engine/data/feeds/rollover.py` — validates per-strategy futures-rollover configuration only.

## Phase 1 data-cleaning module

`engine/data/feeds/data_cleaning.py` — shared timestamp normalization and OHLCV validation helpers.

## Phase 1 importer foundation modules

- `engine/data/feeds/importer_discovery.py` — finds supported incoming files without modifying them.
- `engine/data/feeds/importer_identity.py` — canonical importer identity and timezone contract.
- `engine/data/feeds/importer_detection.py` — deterministic metadata consistency detection.
- `engine/data/feeds/importer_storage.py` — canonical collision-safe Parquet path resolution.
- `engine/data/feeds/importer_reporting.py` — import manifests and quarantine reports.
- `engine/data/feeds/importer_orchestrator.py` — reads incoming files and routes canonical contracts through shared Phase 1 cleaning and storage.

## Rule 7 internal facades

- `engine/audit/log.py` — owns `record(strategy_id, interface_version, exception) -> None` for Rule 7. It is a narrow facade, not the Phase 6 audit-log implementation.
- `engine/safety/strategy_halt.py` — owns `alert_and_halt(strategy_id, exception) -> NoReturn` for Rule 7. It is a narrow facade, not the Phase 7 live-control implementation.
- Future logging and live-control work implements behind these boundaries; it does not change `safe_generate_signal(strategy, data, state, mode)`.

## Build-order mapping (ties to `CLAUDE.md`)

Phase numbers in this table are **build-order** numbers (`CLAUDE.md`), not `requirements-freeze-125.md` document-phase numbers. Numbering equivalence per §123.9: **build-order Phase 6 (Logging) ≡ `requirements-freeze-125.md` Phase 9 (Q88–Q93) plus the Phase 4.5 audit-trail requirement.** Build-order Phase 4 (order abstraction) ≡ freeze-doc Phase 7 (Order Management); build-order Phase 5 (Paper trading) ≡ freeze-doc Phase 6; build-order Phase 7 (Zerodha live) ≡ freeze-doc Phase 7 broker integration + Phase 8 live safety. The freeze document itself is not renumbered. Folder paths below reflect post-migration locations.

| Phase | Folders touched |
|---|---|
| 1. Data layer | `data/`, `engine/data/feeds/`, `engine/data/access.py`, `config/strategies/` — VERIFIED_COMPLETE |
| 2. Backtest engine | `engine/backtest/` (`engine.py`, `validation.py`, `metrics.py`, `walk_forward.py`, `regime.py`, `finalization.py`, `historical_run.py` — structurally relocated from former top-level `engine/*` module paths; contracts unchanged), `strategies/orb/`, `reports/` — VERIFIED_COMPLETE / OWNER_APPROVED (delivered across `engine/` subpackages incl. `costs/`, `reporting/`, `reproducibility/`, `trades/`) |
| 3. Risk mgmt | `engine/risk/risk_manager.py`, `config/risk_config.yaml` — VERIFIED_COMPLETE |
| 4. Order abstraction | `engine/orders/`, `engine/execution/` — VERIFIED_COMPLETE / OWNER_APPROVED |
| 5. Paper trading | `engine/paper/`, `engine/execution/`, `engine/reconciliation/paper/engine.py`, `engine/persistence/` — VERIFIED_COMPLETE / OWNER_APPROVED (external live-market evidence OWNER-DEFERRED) |
| 6. Logging | `logs/` (full build-out), `config/logging_config.yaml`, `CONFIG_SCHEMA.md` §6 — OWNER_APPROVED scope frozen in §123; **implementation NOT STARTED** |
| 7. Zerodha live | `engine/broker_adapters/zerodha_adapter.py`, `config/broker_profiles/`, `engine/data/feeds/upstox/` (provider-specific live feed remains under `engine/data/feeds/`) |
| 9. Dashboard / control surface | `dashboard/` (planned — NOT BUILT) + FastAPI backend; per ADR §131; supersedes earlier "Phase 10"/Streamlit naming |

**Phase-6 authority note (§123.5):** the durable audit journal lives in SQLite (`audit_events` owned by `SQLitePaperStateStore`). Everything under `logs/audit_log/` is a derived, regenerable, non-authoritative export and must never be read back as trading or audit authority, never hand-edited as if it were evidence, and never written by a second writer. Q92 daily summaries and Q93 monthly per-strategy reports remain Phase-6 obligations aggregated only from canonical accounting/trade/leg/cost records (§123.11 items 1–2).

## Rules

- `engine/` contains no strategy-specific code — anything ORB-specific lives only in `strategies/orb/`, per Rule 1's Acceptance Criteria.
- No strategy file imports directly from `engine/data/feeds/` — only from `engine/data/access.py`, per Rule 5.
- Every new strategy gets its own subfolder under `strategies/`, with its own conformance checks — no shared strategy files.
