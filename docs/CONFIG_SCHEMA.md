# SentinelX — Config Schema

**Purpose:** Exact, authoritative schema for every config file the engine reads. Ends guesswork about field names when writing a strategy's YAML.
**Depends on:** `architecture-rules.md` (Rules 1, 2, 5, 6), `requirements-freeze-125.md` (Q13-22, Q55-63).
**Rule:** A field either lives here or it doesn't exist in code. If a new field is needed while coding, add it here first, then use it — never the reverse.

---

## 1. Strategy Config (`config/strategies/<name>.yaml`)

```yaml
# --- Identity (Rule 1, Rule 6) ---
strategy_id: "orb_banknifty_5m"
interface_version: "1.0"              # Rule 6 — must match StrategySignalGenerator.interface_version
strategy_version: "v1.0"               # Q22 — semantic version, separate from interface_version

# --- Data (Rule 3, Rule 5, Q1-3) ---
instrument: "BANKNIFTY"
segment: "futures"                     # per Q2: spot / futures / options
timeframe_primary: "5m"
required_timeframes: ["5m"]            # list — even single-TF strategies use list form (Rule 3)

# --- Futures rollover (Q11) ---
rollover:
  enabled: false
  method: null                          # expiry | volume | open_interest
  expiry_trigger: null
  volume_trigger: null
  open_interest_trigger: null
  missing_data_policy: "error"

# --- State (Rule 2) ---
# Declared here for visibility; actual schema enforced in strategy_base.py
state_schema: {}                       # empty for ORB — no cross-bar state needed

# --- Entry/Exit rules (Q16-21) ---
# Declarative format — only valid for rule-based strategies (Rule 1's
# declarative implementation). State-machine/ML strategies define their
# own internal logic in code and may leave this section minimal.
entry_rules:
  - indicator: "opening_range_high"
    comparison: ">"
    threshold_ref: "current_price"
exit_rules:
  stop_loss:
    type: "atr_based"                  # fixed_pct | atr_based | structure_based (Q18)
    atr_multiplier: 1.5
  target:
    type: "fixed_r_multiple"           # fixed_r_multiple | trailing (Q19)
    r_multiple: 2.0
  trailing_stop: false                 # Q20
  time_based_exit: "15:15"             # mandatory field, Q21 — square-off time (IST)

# --- Warm-up (Phase 4.6) ---
indicator_warmup_bars:
  opening_range_high: 1                # bars needed before this indicator is valid

# --- Regime tagging (Q36) ---
regime_detection: true                 # tag results by trending/sideways/volatile
```

### 1.1 Paper strategy binding (`config/strategies/<name>.yaml`)

The production paper resolver reads this compact, versioned binding format.
It is separate from the historical strategy-design schema above and owns the
exact runtime strategy identity, source stream, and activation class.

```yaml
schema_version: "paper-strategy-config/v1"
strategy_id: "strat_live_paper_default"
strategy_version: "1.0"
activation: "observation_only"        # observation_only | actionable
instrument: "NIFTY"
timeframe: "1m"
protective_policy: null                # required for actionable only
```

The checked-in production paper configuration is observation-only. Generic
`fixed_percent` protection, including any declaration of percentage stop or
target fields, is prohibited for actionable paper strategies. An actionable
binding fails closed before startup until an owner-approved, strategy-owned
policy is implemented and bound to its exact `(strategy_id, strategy_version)`
identity. Observation-only bindings must use `protective_policy: null`.

For an actionable binding, `protective_policy` uses the exact strategy-owned
policy selector envelope below. The enclosing binding supplies the strategy
owner; the resolver requires an exact trusted registration for all four values
and never performs fallback, wildcard, latest-version, or dynamic import
resolution.

```yaml
protective_policy:
  policy_id: "<non-empty exact string>"
  policy_version: "<non-empty exact string>"
  parameters: {}                      # validated only by the selected strategy policy
```

The generic resolver validates only the envelope and canonical parameter
transport. It does not interpret STOP, TARGET, ATR, percentage, R:R, trailing,
or other strategy economics. The registered strategy-owned factory validates
the parameter meaning and returns the required `ProtectivePlanPolicy`.

## 2. Paper Risk Config (`config/risk_config.yaml`)

The active paper resolver accepts only this strict, owner-locked schema. Exact
financial values must be quoted decimal text or integers; YAML floats, NaN,
infinity, malformed, and missing values fail closed.

```yaml
schema_version: "risk-config/v1"
version: "risk-policy/v3"
per_trade_risk_pct: "0.005"
max_daily_loss_pct: "0.02"
max_daily_trades: 10
max_open_positions: 3
max_portfolio_risk_pct: "0.03"
capital_allocation_method: "FIXED"
min_risk_reward: "1.5"
```

### 2.1 Historical schema (not parsed by the paper resolver)

```yaml
# ⚠️ = business decision, from requirements-freeze-125.md — not an architecture default
per_trade_risk_pct: null               # ⚠️ Q55 — your call, suggested default 0.5%
max_daily_loss_pct: null               # ⚠️ Q56 — your call, suggested default 2%
max_daily_trades: 10                   # 🔒 Q57 — already decided
max_open_positions: null               # ⚠️ Q58 — needs correlation-check output first
max_portfolio_risk_pct: null           # ⚠️ Q59 — your call
capital_allocation_method: null        # ⚠️ Q61 — "fixed" | "performance_weighted"
correlation_filter: true               # 🔒 Q60
signal_priority: "confidence_score"    # 🔒 Q62
min_risk_reward: null                  # ⚠️ Q63 — per strategy, your call
```
**These `null` fields must be filled before Phase 3 (Backtesting with real capital assumptions) — see the "Bottom line" numbers-only-you-can-confirm list in `requirements-freeze-125.md`.**

## 3. Execution Config (`config/execution_config.yaml`)

```yaml
execution_model: "next_bar_open"       # 🔒 Q23 — fixed, prevents look-ahead
order_type_default: "market"           # 🔒 Q24
slippage_model:
  futures: "bps_based"                 # 🔒 Q25
  options: "bid_ask_spread_based"
  crypto: "orderbook_depth_based"
brokerage_profile: "zerodha"           # 🔒 Q26 — selects a broker/deployment cost profile; Slice 8 schedule schema remains inactive until implemented
gap_handling:
  simulate_next_day_open: true         # 🔒 Q28
  flag_threshold_atr_multiple: 1.5
walk_forward:
  train_test_ratio: "70/30"            # 🔒 Q31
  min_windows: 3                       # 🔒 Q32 — only once 10-yr data available
monte_carlo:
  enabled: true                        # 🔒 Q33
  random_seed: null                    # 🔒 Phase 4.5 — must be set and stored per run, not left null at runtime
min_trade_count_for_promotion: 200     # 🔒 Q35
```

### 3.1 Paper execution profile

The paper root references one strict execution profile. The only currently
owner-approved profile is explicit and research-only; omission is an error.

```yaml
schema_version: "execution-config/v1"
paper_fill:
  profile: "RESEARCH_ZERO_SLIPPAGE"
  version: "v1"
  slippage_model:
    type: "fixed_bps"
    bps: "0"
  max_execution_tolerance_bps: "500"
  max_slippage_bps: "50"
```

`RESEARCH_ZERO_SLIPPAGE` is identifiable and promotion-ineligible. It is not
an implicit `FixedBasisPointsSlippage(0)` fallback.

### 3.2 Paper cost profile

The paper root must declare the profile's compatible currency explicitly:

```yaml
cost_profile:
  profile: "RESEARCH_ZERO_COST"
  version: "v1"
  currency: "INR"
```

`RESEARCH_ZERO_COST/v1` is a promotion-ineligible INR schedule. The resolver
rejects an account whose `account.currency` is not exactly `cost_profile.currency`
before token access, database creation, account construction, broker creation,
or feed/network construction. No FX conversion or implicit currency inheritance
exists in the paper runtime.

## 4. Broker Profile (`config/broker_profiles/zerodha.yaml`)

```yaml
broker_name: "zerodha"                 # 🔒 Q72 — v1 supports Zerodha only
retry:
  max_attempts: 3                      # 🔒 Q73
  backoff: "exponential"
order_timeout_seconds: 8               # 🔒 Q76 — within the 5-10s range specified
reconciliation_interval_minutes: 5     # 🔒 Q77 — "every N minutes," set here
fee_structure: "zerodha_default"       # 🔒 Q26 — profile identifier only; approved effective-dated cost schedules/rates must be configuration-driven, not hard-coded in calculation logic
```
Credentials (API key/secret) are **never** stored in this file — env vars / `.env` only, per `CLAUDE.md`'s hard rule.

---

## Field Ownership (avoids the exact duplication risk flagged earlier)

| Field category | Authoritative source | This file's role |
|---|---|---|
| Business/risk numbers (risk %, max loss %) | `requirements-freeze-125.md` | Shows where the value is *stored* in config, not what the value *should be* |
| Engineering contract fields (`interface_version`, `state_schema`, `required_timeframes`) | `architecture-rules.md` | Shows exact YAML key names matching the code contract |
| Everything in this file | — | Schema only. No new business or architecture decisions are made here. |

If a value needs deciding (marked ⚠️ above), that decision belongs in `requirements-freeze-125.md`, not here — this file only defines where the decided value lives once made.

---

### 5.0 Historical paper schema (not parsed by the paper resolver)

**Owner-approved scope:** `BACKTEST_ENGINE_ARCHITECTURE_DECISIONS.md` §93 (Owner Decision D13). Paper is a separate controlled operating environment per `requirements-freeze-125.md` deployment-environments requirement.

**Ownership rule:** This file owns paper-environment-specific configuration ONLY. It does NOT duplicate canonical strategy/risk/execution configuration fields. Shared canonical configurations are referenced through their approved identities/fingerprints.

```yaml
# --- Paper Environment Identity ---
environment: "paper"
run_id: null                          # auto-generated per run
promotion_tracking_activated: null    # explicit timestamp when set

# --- Data Source (D1) ---
data_source:
  type: "historical_replay"           # "historical_replay" (Phase 5) | future: "live_websocket"
  replay_config:
    data_path: null                    # path to historical data for replay
    pace: "realtime"                  # "realtime" | "fast_forward"

# --- Execution / Fill Configuration (D4) ---
execution:
  slippage_mode: "canonical"          # "canonical" (backtest-identical) | "zero" | other
  # canonical mode: promotion_eligible = true
  # non-canonical mode: promotion_eligible = false

# --- Cost / Fee Configuration (D5) ---
costs:
  cost_mode: "canonical"             # "canonical" (backtest-identical) | "zero" | other
  # canonical mode: promotion_eligible = true
  # non-canonical mode: promotion_eligible = false

# --- Paper Broker (D6) ---
paper_broker:
  failure_injection:
    enabled: false                    # when true, run is PROMOTION_INELIGIBLE
    rejection_rate: null
    timeout_rate: null

# --- Completed Bar Policy (D3) ---
completed_bar_policy:
  zero_observation: "missing_bar"     # "missing_bar" (D3a) — no synthetic bar

# --- State Persistence (D9) ---
persistence:
  type: "sqlite"                      # SQLite only (§89)
  path: null                          # path to SQLite database

# --- Reconciliation (D7) ---
reconciliation:
  enabled: true
  interval_minutes: null              # inherits from broker_profile if null

# --- Safety (D8) ---
safety:
  kill_switch:
    auto_liquidate_positions: false   # false unless future owner decision
  auto_halt_on_daily_loss: true
  auto_halt_on_error_threshold: true
  heartbeat_enabled: true
  heartbeat_timeout_seconds: null

# --- Canonical Config Bindings ---
canonical_bindings:
  strategy_config_path: null           # references config/strategies/<name>.yaml
  risk_config_path: null               # references config/risk_config.yaml
  execution_config_path: null          # references config/execution_config.yaml
  broker_profile_path: null           # references config/broker_profiles/<name>.yaml
```

## 5. Paper Trading Config (`config/paper_config.yaml`)

This is the required paper-environment root. The resolver completes all
validation before it creates the SQLite store, account, broker, feed, or
transport. Its immutable resolved result is the sole runtime authority.

```yaml
schema_version: "paper-config/v1"
environment: "paper"
account:
  account_id: "ACC_LIVE_PAPER"
  starting_capital: "500000.00"
  currency: "INR"
  monetary_quantum: "0.01"
persistence:
  type: "sqlite"
  path: "../data/paper_trading.db"
canonical_bindings:
  risk_config_path: "risk_config.yaml"
  execution_config_path: "execution_config.yaml"
  strategy_config_paths:
    - "strategies/observational_default.yaml"
cost_profile:
  profile: "RESEARCH_ZERO_COST"
  version: "v1"
  currency: "INR"
```

`RESEARCH_ZERO_COST` is an explicit, versioned existing-cost-engine schedule
with no component rules. It is promotion-ineligible and is never selected by
omitting `cost_profile`. Its INR profile currency must exactly match
`account.currency`. Both research-zero modes expose
`promotion_eligible: false`; no D10 promotion tracking is created here.

---

## 6. Logging Config (`config/logging_config.yaml`) — build-order Phase 6

**Owner-approved scope:** `BACKTEST_ENGINE_ARCHITECTURE_DECISIONS.md` §123.6 (OD-6).
**Status:** PRE-REGISTERED CONTRACT ONLY. The file does **not** exist yet;
creating it is Phase-6 implementation work.

**Ownership rule:** This file owns logging/observability configuration ONLY —
levels, sinks, rotation and retention. It contains zero canonical trading
fields, does NOT amend the frozen Section 5 paper-configuration schema (D13),
and never participates in `configuration_identity`.

Binding contract (per §123.6):

1. Configuration may control **levels, sinks, rotation and retention only**.
2. **Redaction is mandatory and MUST NOT be disableable by configuration.**
   It is a non-optional filter on every sink, not a policy toggle. No secret,
   token or credential is ever written to any sink (Q107, architecture record §118.5).
3. **Required evidence retention is preserved.** The audit journal
   (`audit_events`) and its derived `logs/audit_log/` export are never
   auto-deleted. Error-log retention must cover the §114.13 evidence-retention
   requirement and, where optional promotion tracking is enabled, the active
   promotion-evidence window (the error file is the Q89 detail authority).
   Per §122.35 items 1 and 4 there is no mandatory minimum paper duration and
   no fixed six-month retention floor. Rotation of operational and evaluation
   logs must never reduce evidence retention below the applicable floor.
4. The logging configuration carries its own version identity.

```yaml
# --- PRE-REGISTRATION SKETCH — file not yet created (Phase 6 implementation) ---
schema_version: "<versioned logging-config identity>"   # own version identity (§123.6 item 4)

# Sinks are destinations only. Redaction is applied to EVERY sink by the
# engine itself and is deliberately absent from this file (non-disableable).
sinks:
  trade_log: null        # Q88 trade log (exit reason from lifecycle evidence, §123.7)
  error_log: null        # Q89 error log (sole detail authority: timestamp, stack trace, context)
  strategy_log: null     # Q90 separate NON-audit per-strategy evaluation log incl. HOLD (never enters audit_events, §114.9)
  audit_export: null     # derived, regenerable, NON-authoritative export of SQLite audit_events (§123.5)

levels: {}               # per-sink / per-logger levels only
rotation: {}             # size/time rotation for operational and evaluation sinks
retention: {}            # bounded by the floors of contract item 3; audit journal/export never auto-deleted
```
