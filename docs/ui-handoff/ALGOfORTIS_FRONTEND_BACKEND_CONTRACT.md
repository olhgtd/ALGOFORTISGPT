# AlgoFortis — Frontend / Backend Contract Specification
**Authoritative API Boundary, Request/Response DTOs & Error Handling Contract**
**Product Brand:** AlgoFortis | **Tagline:** Trading Research & Risk OS
**Safety Lock:** `READ_ONLY: true` | `DISARMED: true` | `live_global_hold: true` | `broker mutation: ZERO` | `real broker connection: NONE`

---

## 1. Contract Principles & Architecture Invariants
1. **Fail-Closed Deserialization:** The UI client never invents, guesses, or mocks live trading state. Missing data transitions to `UNAVAILABLE` or `NO_DATA`.
2. **Bearer Authentication:** All non-public endpoints require `Authorization: Bearer <token>` in request headers.
3. **Status Classification:** Every endpoint in this contract is explicitly classified as `ACTIVE / USED TODAY`, `LEGACY / RETIRING`, `DEAD / UNUSED`, or `FUTURE / PLACEHOLDER`.

---

## 2. API Endpoint Matrix & DTO Contracts

### 2.1 Runtime & System Health

#### Endpoint: `GET /api/v1/runtime/status`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Polled heartbeat to determine server readiness, instance lifecycle, and runtime mode.
- **Calling Screen(s):** Global Overlay (`RuntimeAvailability.tsx`), App Boot (`main.tsx`).
- **Request Input:** None (`cache: "no-store"`).
- **Response Fields Used by UI:**
  ```json
  {
    "state": "READY",
    "mode": "standalone_desktop",
    "instance_id": "inst_7f9a2b8c4d1e",
    "api_base": "/api/v1"
  }
  ```
- **Error Codes Handled:** Network timeout, HTTP 500, HTTP 503 -> Triggers `UNAVAILABLE` overlay.
- **Auth Requirement:** Public / None.
- **Role Requirement:** All.
- **Runtime Requirement:** Required at all times.
- **Offline Behavior:** Intercepted by `RuntimeAvailability`; dashboard frozen.

---

#### Endpoint: `GET /api/v1/integration/system/health`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Retrieve database connectivity, SQLite WAL status, schema version, and subsystem health.
- **Calling Screen(s):** Owner Control Center (`AdminHome.tsx`), Admin System Settings (`AdminSecuritySystemSettingsScreen.tsx`).
- **Request Input:** None.
- **Response Fields Used by UI:**
  ```json
  {
    "adapterReachable": true,
    "databaseConnected": true,
    "schemaVersion": 1,
    "journalMode": "wal",
    "auditStoreOperational": true,
    "auditEventCount": 1420,
    "subsystems": {
      "backtest_engine": "HEALTHY",
      "paper_engine": "HEALTHY",
      "market_data": "ONLINE",
      "auth_authority": "OPERATIONAL"
    }
  }
  ```
- **Error Codes Handled:** HTTP 401 (Auth Expired), HTTP 503 (Subsystem down).
- **Auth Requirement:** Bearer Token.
- **Role Requirement:** `OWNER`.
- **Runtime Requirement:** Database online.
- **Offline Behavior:** Displays fallback cached health state marked `STALE`.

---

### 2.2 Authentication & Hardware Passkeys (WebAuthn / FIDO2)

#### Endpoint: `POST /api/v1/auth/webauthn/authentication/options`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Request cryptographic challenge for returning user WebAuthn login.
- **Calling Screen(s):** Secure Entry Gate (`ReturningUserFlow.tsx`).
- **Request Input:**
  ```json
  {
    "identifier": "trader@algofortis.io"
  }
  ```
- **Response Fields Used by UI:**
  ```json
  {
    "challenge_id": "chal_98a7b6c5d4e3f2",
    "publicKey": {
      "challenge": "base64url_string",
      "timeout": 60000,
      "rpId": "localhost",
      "allowCredentials": [],
      "userVerification": "preferred"
    }
  }
  ```
- **Error Codes Handled:** `USER_NOT_FOUND`, `RATE_LIMITED`, `ACCOUNT_SUSPENDED`.
- **Auth Requirement:** None (Pre-auth).
- **Role Requirement:** Public.

---

#### Endpoint: `POST /api/v1/auth/webauthn/authentication/complete`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Submit client authenticator assertion signature to obtain session JWT.
- **Calling Screen(s):** Secure Entry Gate (`ReturningUserFlow.tsx`).
- **Request Input:**
  ```json
  {
    "challenge_id": "chal_98a7b6c5d4e3f2",
    "response": {
      "id": "cred_12345",
      "rawId": "base64url_string",
      "response": {
        "authenticatorData": "base64url_string",
        "clientDataJSON": "base64url_string",
        "signature": "base64url_string",
        "userHandle": "base64url_string"
      },
      "type": "public-key"
    }
  }
  ```
- **Response Fields Used by UI:**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
    "expires_at_utc": "2026-09-15T09:30:00Z",
    "credential_id": "cred_12345",
    "role": "USER",
    "subject": "usr_998877",
    "sx_id": "SX-998877"
  }
  ```
- **Error Codes Handled:** `INVALID_SIGNATURE`, `CHALLENGE_EXPIRED`, `CREDENTIAL_REVOKED`.
- **Auth Requirement:** None (Authenticating).
- **Role Requirement:** Public.

---

#### Endpoint: `POST /api/v1/auth/webauthn/activation/redeem`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Validate single-use invitation token and generate WebAuthn creation challenge.
- **Calling Screen(s):** First-Time Customer Flow (`FirstTimeCustomerFlow.tsx`).
- **Request Input:**
  ```json
  {
    "identifier": "trader@algofortis.io",
    "activation_code": "ACT-8849-UUID-9921"
  }
  ```
- **Response Fields Used by UI:**
  ```json
  {
    "challenge_id": "chal_activation_5544",
    "publicKey": {
      "challenge": "base64url_string",
      "rp": { "name": "AlgoFortis Trading OS", "id": "localhost" },
      "user": { "id": "usr_998877", "name": "trader@algofortis.io", "displayName": "Trader" },
      "pubKeyCredParams": [{ "type": "public-key", "alg": -7 }, { "type": "public-key", "alg": -257 }]
    }
  }
  ```
- **Error Codes Handled:** `TOKEN_INVALID`, `TOKEN_EXPIRED`, `TOKEN_ALREADY_REDEEMED`.
- **Auth Requirement:** Single-use invitation token.

---

#### Endpoint: `POST /api/v1/auth/webauthn/activation/complete`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Store newly registered public key and transition user lifecycle to `ACTIVE`.
- **Calling Screen(s):** First-Time Customer Flow (`FirstTimeCustomerFlow.tsx`).
- **Request Input:**
  ```json
  {
    "challenge_id": "chal_activation_5544",
    "label": "MacBook Pro TouchID",
    "response": { "clientDataJSON": "...", "attestationObject": "..." }
  }
  ```
- **Response Fields Used by UI:**
  ```json
  {
    "registered": true,
    "authentication_required": true
  }
  ```

---

#### Endpoint: `POST /api/v1/auth/webauthn/bootstrap-registration/options` & `/complete`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Appliance first-run bootstrap to enroll the master platform Owner.
- **Calling Screen(s):** Owner Setup Flow (`OwnerSetupFlow.tsx`).
- **Request Header:** `x-sentinelx-bootstrap: <bootstrap_token>`.
- **Response Fields:** `{ "credential_id": "cred_owner_1", "registered": true, "security_setup": "COMPLETED" }`.

---

### 2.3 User & Identity Endpoints

#### Endpoint: `GET /api/v1/users/current`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Retrieve authoritative identity, lifecycle status, service term expiry, and workspace eligibility.
- **Calling Screen(s):** `main.tsx` (`AuthorizedDashboard`), Header, User Settings.
- **Response Fields Used by UI:**
  ```json
  {
    "user_id": "usr_102938",
    "sx_id": "SX-102938",
    "role": "USER",
    "lifecycle": "ACTIVE",
    "account_status": "ACTIVE",
    "activation_status": "COMPLETED",
    "service_status": "ACTIVE",
    "service_started_at": "2026-01-01T00:00:00Z",
    "service_expires_at": "2027-01-01T00:00:00Z",
    "service_term_type": "ANNUAL",
    "custom_term_value": null,
    "display_name": "Senior Quant Trader",
    "namespace": "tenant_default",
    "workspace_eligibility": {
      "user": true,
      "owner": false
    },
    "effective_access": true
  }
  ```
- **Auth Requirement:** Bearer Token.
- **Role Requirement:** Any authenticated user.

---

### 2.4 Owner Access & User Administration

#### Endpoint: `GET /api/v1/integration/access/records`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Read projection of all user activation invitations and redemption history.
- **Calling Screen(s):** Owner Access Registry (`AccessRegistryScreen.tsx`).
- **Response Fields Used by UI:**
  ```json
  {
    "source": "BACKEND",
    "trust": "FRESH",
    "as_of_utc": "2026-09-14T21:00:00Z",
    "total_count": 28,
    "records": [
      {
        "record_id": "rec_001",
        "identifier": "trader@alpha.com",
        "display_name": "Alpha Fund",
        "status": "PENDING",
        "term_type": "ANNUAL",
        "created_at_utc": "2026-09-10T12:00:00Z",
        "expires_at_utc": "2026-10-10T12:00:00Z",
        "reissue_count": 0
      }
    ]
  }
  ```
- **Role Requirement:** `OWNER`.

---

#### Endpoint: `POST /api/v1/owner/access/users`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Create new pre-registered user and issue single-use activation invitation token.
- **Calling Screen(s):** Access Registry Modal (`AccessRegistryScreen.tsx`).
- **Request Input:**
  ```json
  {
    "identifier": "quant@hedgefund.com",
    "display_name": "Hedge Fund Desk 1",
    "term_type": "90_DAYS",
    "custom_days": null,
    "allowed_capabilities": ["BACKTEST", "PAPER", "OPTIONS"]
  }
  ```
- **Response Fields Used by UI:**
  ```json
  {
    "success": true,
    "activation_code": "ACT-7712-4491-UUID",
    "activation_url": "http://127.0.0.1:8080/?surface=secure-entry#first-time"
  }
  ```

---

#### Endpoints: User Lifecycle Administration
- `POST /api/v1/owner/access/users/{id}/suspend` (`ACTIVE / USED TODAY`) -> Instantly suspend account.
- `POST /api/v1/owner/access/users/{id}/restore` (`ACTIVE / USED TODAY`) -> Restore suspended account.
- `POST /api/v1/owner/access/users/{id}/revoke` (`ACTIVE / USED TODAY`) -> Permanent account revocation.
- `POST /api/v1/owner/access/users/{id}/extend-service` (`ACTIVE / USED TODAY`) -> Add days to service term.
- `POST /api/v1/owner/access/users/{id}/renew-service` (`ACTIVE / USED TODAY`) -> Full term renewal.
- `POST /api/v1/owner/access/users/{id}/convert-lifetime` (`ACTIVE / USED TODAY`) -> Convert to lifetime license.

---

### 2.5 Security, Sessions & Device Administration

#### Endpoint: `GET /api/v1/owner/security/sessions` & `POST /revoke`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Real-time active session monitor and remote session kill switch.
- **Calling Screen(s):** Owner Security Screen (`AdminSecuritySystemSettingsScreen.tsx`).
- **Response Fields:** Array of `{ "session_ref", "user_id", "client_ip", "user_agent", "created_at", "last_active_at" }`.

---

#### Endpoint: `GET /api/v1/owner/security/devices` & `POST /revoke`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Enrolled FIDO2 credential registry and hardware key revocation.
- **Calling Screen(s):** Owner Security Screen (`AdminSecuritySystemSettingsScreen.tsx`).

---

### 2.6 Strategy Management & Governance

#### Endpoint: `GET /api/v1/strategies`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** List registered trading strategies for current user or all strategies for Owner.
- **Calling Screen(s):** User Strategies (`UserScreens.tsx`), Backtest Selector (`BacktestingScreen.tsx`), Owner Strategy Governance (`AdminStrategiesScreen.tsx`).
- **Response Fields Used by UI:**
  ```json
  {
    "strategies": [
      {
        "strategy_id": "strat_vwap_cross_v2",
        "name": "Intraday VWAP Momentum",
        "version": "2.1.0",
        "status": "PAPER_APPROVED",
        "base_asset": "BTC/USDT",
        "created_at": "2026-08-01T10:00:00Z",
        "quality_score": 92.4,
        "execution_hold": false
      }
    ]
  }
  ```

---

#### Endpoint: `POST /api/v1/strategies`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Submit and parse new Python strategy script with protective risk policy.
- **Calling Screen(s):** Add Strategy Modal (`AddStrategyModal.tsx`).
- **Request Input:**
  ```json
  {
    "source": "class MomentumStrategy(TradingStrategy): ...",
    "protective_policy_identity": "POL-CONSERVATIVE-MAX-5PCT-DD"
  }
  ```
- **Response Fields Used by UI:**
  ```json
  {
    "accepted": true,
    "strategy_id": "strat_vwap_cross_v2",
    "ast_validation": { "valid": true, "warnings": [] }
  }
  ```

---

#### Endpoint: `POST /api/v1/owner/strategies/{id}/promote`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Owner promotion of strategy from Backtest to Paper or Paper to Live.
- **Calling Screen(s):** Promotion Approval Modal (`AdminStrategiesScreen.tsx`).

---

### 2.7 Backtesting Engine

#### Endpoint: `POST /api/v1/backtest/run`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Launch deterministic historical tick replay engine.
- **Calling Screen(s):** Backtesting Screen (`BacktestingScreen.tsx`).
- **Request Input:**
  ```json
  {
    "strategy_id": "strat_vwap_cross_v2",
    "dataset_id": "BTC-USDT-1M-2024",
    "start_date": "2024-01-01",
    "end_date": "2024-06-30",
    "initial_capital": 100000,
    "slippage_bps": 1.5,
    "commission_rate": 0.0004
  }
  ```
- **Response Fields Used by UI:**
  ```json
  {
    "backtest_id": "bt_run_20260914_8819",
    "status": "RUNNING",
    "estimated_duration_sec": 8
  }
  ```

---

#### Endpoint: `GET /api/v1/backtest/results/{id}`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Retrieve full analytics report, equity curve series, drawdown series, and trade ledger.
- **Calling Screen(s):** Backtesting Analytics (`BacktestingScreen.tsx`).
- **Response Fields Used by UI:**
  ```json
  {
    "backtest_id": "bt_run_20260914_8819",
    "metrics": {
      "net_profit": 34820.50,
      "cagr_pct": 42.1,
      "max_drawdown_pct": 6.8,
      "sharpe_ratio": 2.45,
      "sortino_ratio": 3.12,
      "profit_factor": 2.18,
      "win_rate_pct": 64.2,
      "total_trades": 184
    },
    "equity_curve": [
      { "timestamp": "2024-01-01T00:00:00Z", "equity": 100000 },
      { "timestamp": "2024-01-02T00:00:00Z", "equity": 101250 }
    ],
    "drawdown_series": [
      { "timestamp": "2024-01-01T00:00:00Z", "drawdown_pct": 0.0 }
    ],
    "monthly_returns": {
      "2024": { "Jan": 4.2, "Feb": 3.1, "Mar": -1.2, "Apr": 6.5, "May": 2.8, "Jun": 5.4 }
    },
    "trade_ledger": [
      {
        "trade_id": "tr_001",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "entry_time": "2024-01-02T14:30:00Z",
        "exit_time": "2024-01-02T16:45:00Z",
        "entry_price": 42500.0,
        "exit_price": 43200.0,
        "qty": 1.5,
        "pnl": 1050.0,
        "pnl_pct": 1.64,
        "slippage_paid": 6.37
      }
    ]
  }
  ```

---

### 2.8 Market Data & Charting

#### Endpoint: `GET /api/v1/market/chart`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Authoritative OHLCV candlestick series for interactive charts.
- **Calling Screen(s):** `ProfessionalChart.tsx`, User Dashboard Home, Paper Trading.
- **Query Params:** `instrument`, `timeframe` (1m, 5m, 1h, 1d), `mode` (`LIVE`, `FROZEN_HISTORICAL`, `BACKTEST`), `start_date`, `end_date`, `limit`.
- **Response Fields Used by UI:**
  ```json
  {
    "instrument": "BTC/USDT",
    "timeframe": "1h",
    "candles": {
      "state": "AVAILABLE",
      "value": [
        { "time": "2026-09-14T20:00:00Z", "open": 58400.0, "high": 58900.0, "low": 58350.0, "close": 58750.0, "volume": 142.5 }
      ]
    }
  }
  ```
- **Error States Handled:** `NO_DATA`, `DATA_PROVIDER_NOT_CONFIGURED`, `BACKEND_UNAVAILABLE`.

---

### 2.9 Orders, Positions & Portfolio Oversight

#### Endpoint: `GET /api/v1/{owner|user}/orders-portfolio?mode={PAPER|BACKTEST|SHADOW|LIVE}`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Consolidated runtime snapshot of active accounts, open positions, working orders, and execution events.
- **Calling Screen(s):** User Portfolio (`UserScreens.tsx`), Owner Portfolio Oversight (`AdminPortfolioOrdersScreen.tsx`), Shared Runtime (`OrdersPortfolioRuntime.tsx`).
- **Response Fields Used by UI:**
  ```json
  {
    "execution_mode": "PAPER",
    "availability": "AVAILABLE",
    "source": "SIMULATED_MATCHING_ENGINE",
    "accounts": [
      { "account_id": "sim_acc_01", "currency": "USD", "balance": 105420.0, "available_margin": 84200.0 }
    ],
    "positions": [
      { "symbol": "BTC/USDT", "side": "LONG", "qty": 0.5, "entry_price": 57800.0, "current_price": 58750.0, "unrealized_pnl": 475.0 }
    ],
    "orders": [
      { "order_id": "ord_88192", "symbol": "BTC/USDT", "side": "BUY", "type": "LIMIT", "qty": 0.25, "price": 57500.0, "status": "WORKING" }
    ],
    "events": []
  }
  ```

---

### 2.10 Regulatory Audit & Compliance

#### Endpoint: `GET /api/v1/audit/events` & `GET /api/v1/integration/audit/events`
- **Status:** `ACTIVE / USED TODAY`
- **Purpose:** Immutable D16 append-only security and trading audit event ledger.
- **Calling Screen(s):** Owner Audit Screen (`AdminReportsAuditScreen.tsx`).
- **Response Fields Used by UI:** Array of `{ "id", "timestamp_utc", "actor_id", "event_type", "resource_id", "status", "integrity_hash", "metadata" }`.

---

## 3. Legacy, Unused & Future Endpoints

| Endpoint | Classification | Description / Migration Path |
|---|---|---|
| `POST /api/v1/auth/legacy/login` | `DEAD / UNUSED` | Removed in favor of WebAuthn Passkeys. Fails closed with HTTP 410 Gone. |
| `POST /api/v1/orders/live` | `DISARMED / SAFETY LOCKED` | Live broker mutation endpoint. Permanently returns `{ mutation_allowed: false, reason: "SAFETY_LOCK_ENGAGED" }`. |
| `GET /api/v1/cloud/sync` | `FUTURE / PLACEHOLDER` | Reserved for optional central identity synchronization in multi-node clusters. |
