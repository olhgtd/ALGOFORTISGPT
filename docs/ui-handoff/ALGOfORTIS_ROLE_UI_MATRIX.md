# AlgoFortis — Role & Permission UI Capability Matrix
**Authoritative RBAC Invariants & Workspace Boundary Contract**
**Product Brand:** AlgoFortis | **Tagline:** Trading Research & Risk OS
**Safety Lock:** `READ_ONLY: true` | `DISARMED: true` | `live_global_hold: true` | `broker mutation: ZERO` | `real broker connection: NONE`

---

## 1. Role Definitions & Access Invariants
1. **`PUBLIC`**: Unauthenticated browser client. Restricted to marketing, technical specifications, and authentication challenge screens.
2. **`USER` (Trader / Researcher)**: Authenticated customer. Operates within their own tenant sandbox. Authorized to author strategies, run backtests, execute paper trading, manage personal passkeys, and view personal portfolio evidence.
3. **`OWNER` (Platform Administrator)**: Appliance administrator. Governs access tokens, user lifecycles, global risk allowances, strategy promotion, system persistence, security policies, and regulatory audit records.

### Critical Safety Invariants (Forbidden Powers):
- **Owner CANNOT trade on behalf of users** or place live orders under a user's identity.
- **Owner CANNOT view or access user-encrypted private keys** or sensitive trading secrets.
- **Neither Owner nor User can bypass the Live Safety Lock** (`READ_ONLY = true`, `DISARMED = true`, `broker mutation = ZERO`).

---

## 2. Feature & Screen Capability Matrix

| Feature / Screen Surface | Public | User | Owner | View | Create | Edit | Delete / Revoke | Special Notes & Invariants |
|---|---|---|---|---|---|---|---|---|
| **Public Landing & Docs (`PUB-001`)** | ✅ Allowed | ✅ Allowed | ✅ Allowed | ✅ Full | ❌ No | ❌ No | ❌ No | Static public documentation and capability showcase. |
| **Secure Entry Gate (`AUTH-001`)** | ✅ Allowed | ✅ Allowed | ✅ Allowed | ✅ Full | ✅ Passkey | ❌ No | ❌ No | Public entry gate for WebAuthn authentication ceremonies. |
| **Owner Control Center (`OWN-001`)** | ❌ Blocked | ❌ Blocked | ✅ Allowed | ✅ Owner | ❌ No | ✅ Policy | ❌ No | System health, persistence overview, and global hold toggle. |
| **Access Registry (`OWN-002`)** | ❌ Blocked | ❌ Blocked | ✅ Allowed | ✅ Owner | ✅ Tokens | ✅ Term | ✅ Revoke | Token issuance and customer onboarding registry. |
| **User Directory (`OWN-003`)** | ❌ Blocked | ❌ Blocked | ✅ Allowed | ✅ Owner | ❌ Users self-enroll | ✅ Status | ✅ Suspend/Revoke | Owner cannot delete users without audit log confirmation. |
| **Owner Security & Devices (`OWN-004`)** | ❌ Blocked | ❌ Blocked | ✅ Allowed | ✅ Global | ❌ No | ✅ Limits | ✅ All Sessions | Remote kill-switch for suspicious sessions/devices. |
| **Strategy Governance (`OWN-005`)** | ❌ Blocked | ❌ Blocked | ✅ Allowed | ✅ All Strats | ❌ User only | ✅ Limits | ✅ Quarantine | Approve/reject user promotion requests; set risk bounds. |
| **Owner Portfolio Oversight (`OWN-007`)** | ❌ Blocked | ❌ Blocked | ✅ Allowed | ✅ Read-only | ❌ Cannot trade | ❌ No | ❌ No | Institutional read projection of simulated positions. |
| **Plugin & Gateway Registry (`OWN-008`)** | ❌ Blocked | ❌ Blocked | ✅ Allowed | ✅ Owner | ✅ Plugin | ✅ Config | ✅ Disable | Manage broker adapters and market data gateways. |
| **Regulatory Audit Trail (`OWN-009`)** | ❌ Blocked | ❌ Blocked | ✅ Allowed | ✅ Read-only | ❌ Append-only | ❌ Immutable | ❌ Never deleted | D16 compliance ledger; exports cryptographic reports. |
| **Trader Overview (`USR-001`)** | ❌ Blocked | ✅ Allowed | ✅ Workspace switch | ✅ Own account | ❌ No | ❌ No | ❌ No | Personal portfolio equity curve and paper metrics. |
| **User Strategy Catalog (`USR-002`)** | ❌ Blocked | ✅ Allowed | ✅ Workspace switch | ✅ Own strats | ✅ New Strat | ✅ Params | ✅ Archive | User authors and edits their personal trading scripts. |
| **Deterministic Backtesting (`USR-003`)** | ❌ Blocked | ✅ Allowed | ✅ Workspace switch | ✅ Own runs | ✅ Run BT | ❌ Replay is fixed | ✅ Delete run | Tick-level historical simulation laboratory. |
| **Paper Trading Center (`USR-004`)** | ❌ Blocked | ✅ Allowed | ✅ Workspace switch | ✅ Own paper | ✅ Sim Orders | ✅ Orders | ✅ Cancel Orders | Zero financial risk simulated execution daemon. |
| **User Orders Ledger (`USR-005`)** | ❌ Blocked | ✅ Allowed | ✅ Workspace switch | ✅ Own orders | ❌ Via engine | ❌ No | ❌ No | Searchable execution history across Backtest/Paper. |
| **Market Connections (`USR-006`)** | ❌ Blocked | ✅ Allowed | ✅ Workspace switch | ✅ Allowed feeds | ❌ No | ❌ No | ❌ No | View permitted symbols and data feed health. |
| **Options Analytics (`USR-008`)** | ❌ Blocked | ✅ Allowed | ✅ Workspace switch | ✅ Full | ✅ Strategies | ✅ Legs | ✅ Clear legs | Greeks modeling and multi-leg strategy constructor. |
| **Personal Security (`USR-009`)** | ❌ Blocked | ✅ Allowed | ✅ Workspace switch | ✅ Own keys | ✅ Add Passkey | ✅ Rename | ✅ Backup key | Manage personal FIDO2 credentials and sessions. |
| **Global Safe Mode Toggle** | ❌ Blocked | ❌ Blocked | ✅ Allowed | ✅ Owner | ❌ No | ✅ Engage/Hold | ❌ No | Master platform emergency freeze switch. |
| **Live Broker Mutation** | ❌ Blocked | ❌ Blocked | ❌ Blocked | ❌ No | ❌ No | ❌ No | ❌ No | **PERMANENTLY DISARMED AND LOCKED ACROSS ALL ROLES**. |
