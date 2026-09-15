# AlgoFortis — UI Data Field Dictionary
**Authoritative User-Visible Data Schema, Types, Formatting & Validation Dictionary**
**Product Brand:** AlgoFortis | **Tagline:** Trading Research & Risk OS
**Safety Lock:** `READ_ONLY: true` | `DISARMED: true` | `live_global_hold: true` | `broker mutation: ZERO` | `real broker connection: NONE`

---

## 1. User, Identity & Session Fields

| Field Key | Display Name | Source / DTO | Type | Format / Example | Null / Empty Behavior | Role Visibility | Editable? | Validation Rules |
|---|---|---|---|---|---|---|---|---|
| `user_id` | User Identifier | `AuthoritativeUserResponse` | String | `usr_98a7b6c` | N/A (Required) | All | No | Read-only unique internal identifier. |
| `sx_id` | Sentinel/AlgoFortis ID | `AuthoritativeUserResponse` | String | `SX-10492` | N/A | All | No | Prefix `SX-` followed by 5 digits. |
| `display_name` | Display Name | `AuthoritativeUserResponse` | String | `"Alpha Quant Desk"` | Displays `user_id` | All | Yes (Owner) | 2–64 characters, sanitized UTF-8. |
| `role` | Role | `AuthoritativeUserResponse` | Enum | `OWNER` \| `USER` | N/A | All | No | Strict RBAC enum. |
| `lifecycle` | Account Lifecycle | `AuthoritativeUserResponse` | Enum | `ACTIVE` \| `PENDING` \| `SUSPENDED` | Default `PENDING` | All | Yes (Owner) | Governed by Owner lifecycle APIs. |
| `service_status` | Service Status | `AuthoritativeUserResponse` | Enum | `ACTIVE` \| `EXPIRED` | Default `ACTIVE` | All | Yes (Owner) | Computed from expiration timestamp. |
| `service_expires_at` | Expiration Date | `AuthoritativeUserResponse` | ISO 8601 String | `2027-01-01T00:00:00Z` | Displays "Lifetime" | All | Yes (Owner) | Valid future UTC timestamp or `null`. |
| `session_ref` | Session ID | `OwnerSessionRow` | String | `sess_4482a9` | N/A | Owner, User (own) | No | Cryptographic session reference. |
| `client_ip` | IP Address | `OwnerSessionRow` | String | `192.168.1.100` | Displays "Unknown" | Owner, User (own) | No | IPv4 or IPv6 format. |

---

## 2. Strategy & Governance Fields

| Field Key | Display Name | Source / DTO | Type | Format / Example | Null / Empty Behavior | Role Visibility | Editable? | Validation Rules |
|---|---|---|---|---|---|---|---|---|
| `strategy_id` | Strategy Identifier | `StrategyRow` | String | `strat_vwap_mom_v2` | N/A | Owner, User | No | Alphanumeric, underscores, hyphens. |
| `strategy_name` | Strategy Name | `StrategyRow` | String | `"VWAP Momentum"` | Displays `strategy_id` | Owner, User | Yes (User) | 1–64 alphanumeric characters. |
| `version` | Version Tag | `StrategyRow` | String | `"2.1.0"` | Default `"1.0.0"` | Owner, User | Yes (User) | Semver `X.Y.Z` format. |
| `governance_state` | Governance State | `StrategyRow` | Enum | `DRAFT` \| `BACKTEST_ONLY` \| `PAPER_APPROVED` \| `LIVE_PROMOTED` \| `QUARANTINED` | Default `DRAFT` | Owner, User | Yes (Owner) | State machine transition governed by Owner. |
| `quality_score` | Compliance Score | `StrategyQualityResult` | Float | `94.5 / 100` | Displays `"--"` | Owner, User | No | Calculated score (0.0 – 100.0). |
| `execution_hold` | Execution Hold | `StrategyRow` | Boolean | `true` \| `false` | Default `false` | Owner, User | Yes (Owner) | Boolean safety lock flag. |
| `max_lot_size` | Max Allowable Lots | `StrategyAllowance` | Integer | `10 Lots` | Displays "No Limit" | Owner, User | Yes (Owner) | Min: 1, Max: 10,000. |

---

## 3. Backtest & Performance Metric Fields

| Field Key | Display Name | Source / DTO | Type | Format / Example | Null / Empty Behavior | Role Visibility | Editable? | Validation Rules |
|---|---|---|---|---|---|---|---|---|
| `net_profit` | Net Profit | `BacktestResult.metrics` | Currency Float | `+$34,820.50` | Displays `"$0.00"` | User, Owner | No | Formatted with 2 decimals, colored green/red. |
| `cagr_pct` | Compound Annual Growth | `BacktestResult.metrics` | Percentage Float | `+42.10%` | Displays `"--%"` | User, Owner | No | Annualized return percentage. |
| `max_drawdown_pct` | Max Drawdown | `BacktestResult.metrics` | Percentage Float | `-6.80%` | Displays `"0.00%"` | User, Owner | No | Peak-to-trough percentage decline. |
| `sharpe_ratio` | Sharpe Ratio | `BacktestResult.metrics` | Float | `2.45` | Displays `"--"` | User, Owner | No | Risk-adjusted return metric. |
| `profit_factor` | Profit Factor | `BacktestResult.metrics` | Float | `2.18` | Displays `"--"` | User, Owner | No | Gross Profits / Gross Losses. |
| `win_rate_pct` | Win Rate | `BacktestResult.metrics` | Percentage Float | `64.20%` | Displays `"--%"` | User, Owner | No | Winning trades / Total trades. |
| `total_trades` | Total Executed Trades | `BacktestResult.metrics` | Integer | `184` | Displays `"0"` | User, Owner | No | Integer trade count >= 0. |

---

## 4. Paper Trading, Orders & Execution Fields

| Field Key | Display Name | Source / DTO | Type | Format / Example | Null / Empty Behavior | Role Visibility | Editable? | Validation Rules |
|---|---|---|---|---|---|---|---|---|
| `order_id` | Order Ref ID | `RuntimeEvidence` | String | `ord_88192` | N/A | User, Owner | No | Microsecond-prefixed UUID. |
| `symbol` | Ticker Symbol | `RuntimeEvidence` | String | `"BTC/USDT"` | N/A | User, Owner | No | Standard uppercase pair formatting. |
| `side` | Order Side | `RuntimeEvidence` | Enum | `BUY` \| `SELL` | N/A | User, Owner | No | Colored: `BUY` (Green), `SELL` (Red). |
| `order_type` | Order Type | `RuntimeEvidence` | Enum | `LIMIT` \| `MARKET` \| `STOP` | Default `LIMIT` | User, Owner | No | Supported execution order types. |
| `qty` | Quantity | `RuntimeEvidence` | Float | `1.5000` | N/A | User, Owner | No | Formatted according to instrument lot step. |
| `price` | Order Limit Price | `RuntimeEvidence` | Currency Float | `$58,400.00` | Displays `"MARKET"` | User, Owner | No | Formatted with tick precision. |
| `order_status` | Status | `RuntimeEvidence` | Enum | `WORKING` \| `FILLED` \| `CANCELLED` \| `REJECTED` | N/A | User, Owner | No | Real-time state pill. |
| `unrealized_pnl` | Open PnL | `RuntimeEvidence` | Currency Float | `+$475.00 (+1.2%)` | Displays `"$0.00"` | User, Owner | No | Dynamic mark-to-market calculation. |

---

## 5. Security, Hardware Devices & Audit Fields

| Field Key | Display Name | Source / DTO | Type | Format / Example | Null / Empty Behavior | Role Visibility | Editable? | Validation Rules |
|---|---|---|---|---|---|---|---|---|
| `credential_id` | Passkey ID | `OwnerDeviceRow` | String | `cred_88a91c` (Truncated) | N/A | Owner, User (own) | No | Base64URL credential identifier hash. |
| `device_label` | Key Friendly Name | `OwnerDeviceRow` | String | `"YubiKey 5C NFC Primary"` | Displays `"Security Key"` | Owner, User | Yes | 1–48 characters. |
| `registered_at` | Enrolled Date | `OwnerDeviceRow` | ISO 8601 String | `2026-08-15T14:20:00Z` | N/A | Owner, User | No | Formatted as `MMM DD, YYYY HH:mm UTC`. |
| `audit_event_id` | Audit ID | `AuditEntry` | String | `evt_991823` | N/A | Owner | No | Chronological D16 ledger event ID. |
| `event_type` | Event Classification | `AuditEntry` | Enum | `AUTH_SUCCESS` \| `STRATEGY_PROMOTED` \| `HOLD_ENGAGED` | N/A | Owner | No | D16 audit event taxonomy. |
| `integrity_hash` | SHA256 Checksum | `AuditEntry` | Hex String | `e3b0c44298fc1c149afbf4c8996fb9...` | N/A | Owner | No | 64-character lowercase hexadecimal hash. |
