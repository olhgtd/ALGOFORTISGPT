# AlgoFortis V2 Phase 6 — Isolated Angel One Live V2 Read-Only Design

**Date:** 2026-09-27  
**Status:** OWNER-APPROVED DESIGN / IMPLEMENTATION NOT YET QUALIFIED  
**Phase:** Phase 6 — Live Execution V2 (still READ_ONLY / DISARMED)  
**Authority:** `docs/v2/adr/ADR-015-phase6-live-safety-policy.md`, `docs/v2/phase6/PHASE6_OWNER_DECISION_FREEZE.md`, Owner approval of Option B on 2026-09-27.

## 1. Purpose

Phase 6 introduces the first production-shaped real-broker boundary without enabling real-money order mutation. The selected architecture is **Option B: a new isolated Angel One Live V2 boundary**. The existing legacy `engine/broker_adapters/angel_adapter.py` remains unchanged and is not promoted into the Phase-6 production authority path.

The Phase-6 adapter is a broker-truth provider. It may authenticate, observe, normalize, and report broker state required for reconciliation and qualification. It does **not** become a reconciliation authority, risk authority, arm authority, order approval authority, or autonomous recovery authority.

> **G6 GREEN does not mean real-money trading is enabled.** G6 is a DISARMED/read-only qualification gate. A successful G6 must leave Live mutation structurally unreachable and Live state `READ_ONLY / DISARMED`. Any later mutation enablement requires a separate dated design, qualification evidence, release gate, and explicit Owner authorization.

## 2. Non-goals

Phase 6 does not:

- enable `place`, `modify`, `cancel`, GTT creation/modification/cancellation, or any equivalent broker mutation;
- turn `LiveStateMachine` arming on;
- permit restart, reconnect, token refresh, device/session recovery, or cloud recovery to auto-arm;
- create a second reconciliation engine;
- create a second incident/alert framework;
- hard-code broker throttling, exchange limits, square-off times, or other production policy values in application modules;
- allow AI, strategy, UI, account/cloud, alert, reconciliation, or broker-observation code to mint `ApprovedOrder` or gain direct mutation authority;
- treat G6 as authorization for a live pilot.

## 3. Architectural ownership

### 3.1 Angel One Live V2 adapter — broker truth only

A new focused package under `engine/broker_adapters/angelone_v2/` owns the production-shaped Angel One read-only boundary.

It is responsible for:

- explicit credential/config validation;
- current SmartAPI endpoint configuration;
- authentication/session establishment and refresh observation;
- read-only orders, trades/fills, positions, funds/RMS, profile/health queries required by reconciliation;
- normalization into existing broker contracts;
- capability reporting;
- broker/request failure classification;
- versioned broker rate-policy consumption;
- static-IP/config eligibility evidence;
- daily-session boundary evidence;
- broker/exchange rule-policy evidence;
- broker-protective-capability observation.

It is not responsible for:

- deciding whether broker/local state matches;
- classifying foreign activity as an operational verdict;
- changing Live safety state;
- dispatching alerts directly;
- adopting broker-only orders/positions;
- creating/cancelling/modifying any broker order during G6.

### 3.2 Reconciliation authority — reuse `engine/reconciliation/live_reconciler.py`

The Phase-6 V2 adapter supplies normalized broker truth to the existing live reconciliation authority.

**Binding rule:** **the V2 adapter provides broker truth; `engine/reconciliation/live_reconciler.py` provides the reconciliation verdict.**

No third reconciler is introduced. Any Phase-6 changes to `live_reconciler.py` must be additive, broker-neutral, deterministic, and preserve its role as the single Live reconciliation verdict authority.

The reconciler may classify:

- matched known order/position state;
- missing broker state;
- broker-only/foreign orders;
- broker-only/foreign positions;
- status/fill divergence;
- unavailable/uncertain broker truth.

Classification does not itself perform broker mutation.

### 3.3 Foreign-activity incident authority — reuse Phase-5 evidence/alert model

OD-V2-06 foreign activity must reuse the existing Phase-5 incident and alert trail:

- `engine.paper.contracts_v2.FailureIncident` remains the shared auditable incident schema unless a separately reviewed generic extraction is required;
- `FailureSeverity` remains the severity vocabulary;
- `engine.alerts.contracts.AlertEnvelope` remains the redacted alert envelope;
- `engine.alerts.dispatcher.AlertDispatcher` remains the independent fan-out dispatcher;
- existing local and Telegram alert adapters remain independent delivery channels.

Phase 6 extends the incident vocabulary with deterministic failure types such as `FOREIGN_BROKER_ORDER`, `FOREIGN_BROKER_POSITION`, `BROKER_TRUTH_UNAVAILABLE`, `BROKER_SESSION_INVALID`, and `BROKER_RATE_POLICY_BLOCK` without creating a parallel incident stack.

Foreign activity must:

1. emit an auditable incident;
2. halt new-entry eligibility for the affected account/context;
3. dispatch a critical/recovery-required alert through the existing dispatcher;
4. remain unresolved until explicit reconciliation/recovery evidence exists;
5. never be ignored, silently adopted, or automatically cancelled/modified.

Any later manual adoption workflow is out of scope for this design.

### 3.4 Live safety state authority

`engine/live/state_machine_v2.py` remains the Live safety-state authority. Phase 6 may observe or request fail-closed state transitions through an explicit coordinator, but broker adapter code must not mutate state directly.

Throughout G6 qualification:

- `arm_enabled=False` remains the effective runtime condition;
- restart/crash/reconnect restore paths remain non-arming;
- no broker response can produce `ACTIVE`;
- successful authentication/reconciliation does not imply entry permission.

### 3.5 Risk authority

`RiskGate` and the existing `ApprovedOrder` capability remain the only future executable-order approval authority. Phase-6 read-only code must not import, construct, mint, deserialize into, or transport an `ApprovedOrder` to a real broker mutation path.

## 4. Structural mutation firewall

Mutation-unreachability is an architectural property, not a runtime flag convention.

Create `build/tools/check_phase6_live_readonly.py` as a source-level CI guard modeled after the Phase-5 static guard.

The guard must fail if the G6 production path can structurally reach broker mutation. At minimum it must verify:

1. Phase-6 Angel One V2 production modules expose no callable production mutation entrypoints such as `place`, `submit`, `modify`, `cancel`, `create_gtt`, `modify_gtt`, or `cancel_gtt`.
2. Phase-6 coordinator/reconciliation/incident modules do not invoke those names on a broker object.
3. Phase-6 read-only modules do not import legacy mutation-capable `engine.broker_adapters.angel_adapter.AngelOneBrokerAdapter`.
4. Phase-6 modules do not import execution mutation modules or construct `ApprovedOrder`.
5. Live default arming remains disabled and Phase-6 code cannot set `arm_enabled=True`.
6. No environment/config flag can bypass the structural block.
7. The required Phase-6 tests/evidence files are present.

Synthetic negative-fixture tests must prove the guard rejects an intentionally unsafe file even if that file carries a `DISARMED=True` or similar flag.

## 5. New module boundaries

Expected focused modules:

- `engine/broker_adapters/angelone_v2/__init__.py` — exports the V2 read-only surface.
- `engine/broker_adapters/angelone_v2/contracts.py` — immutable read-only broker configuration, policy references, capability/status contracts.
- `engine/broker_adapters/angelone_v2/read_only_adapter.py` — current SmartAPI read-only transport/normalization only.
- `engine/broker_adapters/angelone_v2/session.py` — explicit auth/session lifecycle and daily-boundary semantics; no trading mutation.
- `engine/broker_adapters/angelone_v2/rate_policy.py` — versioned injected rate-policy contracts/evaluator; no guessed production constants.
- `engine/broker_adapters/angelone_v2/compliance_gate.py` — static-IP/API/rule-policy eligibility evidence; no arm authority.
- `engine/broker_adapters/angelone_v2/protection_capability.py` — observes whether required broker-resident protection semantics are supported/configurable.
- `engine/live/phase6_readonly_coordinator.py` — composes observation, existing reconciler, incident creation, alert dispatch, and fail-closed state response without broker mutation.
- `build/tools/check_phase6_live_readonly.py` — static mutation-firewall and policy guard.
- `build/tools/phase6_probe.py` — deterministic G6 evidence probe.

Large legacy files are not rewritten merely to fit this design.

## 6. Read-only broker contract

The G6 adapter surface must be explicitly read-only. The concrete production object should expose only the minimum methods required for qualification, for example:

```python
class AngelOneReadOnlyPort(Protocol):
    descriptor: BrokerPortDescriptor

    def capabilities(self) -> frozenset[str]: ...
    def profile(self) -> object: ...
    def orders(self) -> tuple[BrokerAdapterOrderSnapshot, ...]: ...
    def trades(self) -> tuple[BrokerFillFragment, ...]: ...
    def positions(self) -> tuple[BrokerPositionSnapshot, ...]: ...
    def funds(self) -> BrokerFundsSnapshot: ...
    def health(self) -> object: ...
```

If the existing `LiveBrokerReconciler` requires the legacy query names (`query_open_orders`, `query_positions`, `query_funds`), use a narrow read-only compatibility facade. Do not add mutation methods solely to satisfy an older broad `BrokerAdapter` protocol.

## 7. Authentication, credential, and endpoint rules

Phase-6 V2 must not copy legacy fallback behavior.

Required properties:

- no default/fake API key;
- no fake client IP, public IP, MAC address, or successful broker response;
- missing credentials fail closed;
- `http_client=None` must not simulate success in production-shaped code;
- endpoints are supplied by a versioned broker profile, not copied from legacy constants;
- credentials/tokens are injected through the existing secret boundary and never committed/logged/audited in plaintext;
- authentication success grants observation capability only, never mutation or arm capability;
- token expiry/refresh failure results in unavailable/degraded broker truth and a fail-closed incident path.

## 8. Rate limiting and storm behavior

Broker limits are policy data, not source constants.

Reuse the Phase-5 pattern established by `FailureStormPolicy`: a versioned policy object is injected, and absence/invalidity fails closed.

Phase-6 rate policy must distinguish at least:

- authentication/session calls;
- order-book/read queries;
- position/funds/profile reads;
- future mutation class (represented as policy metadata only during G6; no callable mutation path).

The current Angel One/NSE values recorded in the dated G6 broker-rule review are evidence inputs. They are not embedded as unversioned application constants. If current authoritative documentation changes, a new policy/evidence version is required.

Repeated 429/rate-limit responses, auth failures, timeouts, or reconnect storms must feed the shared failure/incident machinery. Missing rate policy must not permit unbounded retry.

## 9. Session and day-boundary behavior

The adapter/session layer must explicitly model:

- authenticated vs unauthenticated/unverifiable session;
- access/refresh token validity evidence;
- broker daily session/logout boundary where applicable;
- reconnect after network loss;
- restart recovery;
- clock/time evidence required by current broker/exchange policy.

Restart, session refresh, or reconnect must never auto-arm. New-entry eligibility stays false until the existing safety/reconciliation authorities say the system is ready under a later authorized mutation design.

## 10. Static-IP and broker-rule eligibility

The compliance gate is evidence-only and fail-closed. It must be able to represent:

- policy profile id/version;
- broker/app identity reference;
- registered-static-IP requirement status;
- observed/declared execution-origin eligibility evidence;
- broker/exchange rule-review version/date;
- supported order types/products;
- tagging/OPS policy reference;
- protective-order capability reference;
- unresolved/pending external requirements.

A missing, stale, contradictory, or unverifiable required item returns `NOT_ELIGIBLE` / `UNVERIFIED` and cannot create arm authority.

## 11. Market-order and order-type policy

The dated 2026-09-27 rule review records the current NSE retail-algo restriction that algo Market Orders are not permitted.

For G6:

- no real order mutation exists anyway;
- any order-policy validator/probe must deterministically reject `MARKET` for the selected retail-algo path;
- no code may silently convert a Market request to Limit;
- IOC/product/order-type eligibility is driven by versioned broker/exchange policy evidence;
- unknown order type/product eligibility fails closed.

This rule is evidence-driven and must be re-verified at the later mutation/release gate rather than assumed permanent.

## 12. Foreign broker activity and exclusivity

Broker truth inconsistent with AlgoFortis-owned known state is foreign activity under OD-V2-05/06.

The coordinator must consume a reconciliation verdict and produce the shared incident/alert response. It must not infer ownership from weak metadata alone.

Required outcomes:

- broker-only order -> foreign-order incident + halt new entries + alert;
- broker-only position -> foreign-position incident + halt new entries + alert;
- unknown ownership / incomplete broker truth -> uncertainty incident + fail closed;
- repeated observations remain idempotent/auditable rather than generating uncontrolled alert storms;
- no automatic adoption;
- no automatic cancellation/modification;
- no cloud record may override a local fail-closed verdict.

## 13. Broker-resident protective capability

OD-V2-08 is a qualification requirement, not permission to place protective orders during G6.

The Phase-6 capability observer must record whether the selected broker/API can represent the protective semantics required by frozen strategy/risk policy. Missing or unknown required capability keeps that future mutation path DISARMED.

G6 may verify capability metadata and read existing broker-resident protection where observable. It must not create/modify protection on the broker.

## 14. Deterministic G6 evidence

`build/tools/phase6_probe.py` must emit machine-comparable evidence with no broker secrets or live mutation.

Required markers include at least:

- `G6_SCHEMA_VERSION`
- `BROKER=ANGELONE`
- `BROKER_BOUNDARY=V2_ISOLATED_READ_ONLY`
- `RECONCILIATION_AUTHORITY=LIVE_RECONCILER`
- `FOREIGN_ACTIVITY_INCIDENT_MODEL=PHASE5_SHARED`
- `LIVE_STATE=READ_ONLY/DISARMED`
- `REAL_BROKER_MUTATION_CAPABILITY=ABSENT`
- `AUTO_ARM_ON_RECONNECT=FALSE`
- `MARKET_ORDER_POLICY=FAIL_CLOSED`
- `STATIC_IP_POLICY=VERSIONED_REQUIRED_EVIDENCE`
- `RATE_POLICY=VERSIONED_INJECTED`
- `FOREIGN_ACTIVITY_ACTION=HALT_ALERT_MANUAL_ONLY`
- deterministic aggregate fingerprint.

The cross-Windows G6 compare gate must require identical evidence and preserve prior G4/G5/GP-S2 evidence where those dependencies are part of the stack.

## 15. Current external rule inputs — dated 2026-09-27

This section is an engineering/compliance input under OD-V2-09, not legal advice and not a permanent runtime constant source.

Verified current inputs:

1. **Angel One SmartAPI static-IP rule:** Angel One's exchange-regulations page states that from 2026-04-01, API order execution is accepted only from the registered Static IP.
2. **Angel One SmartAPI order API throttling:** current SmartAPI docs state that place/modify/cancel order API requests share a combined cap of 9 requests/second, with additional minute/hour limits documented by the broker.
3. **SEBI implementation timeline:** SEBI's 2025-09-30 circular states that from 2026-04-01 the retail-algo framework and exchange implementation standards are applicable to all stock brokers.
4. **NSE retail-algo API classification/tagging:** the current NSE FAQ states that orders received through client APIs are considered Algo orders and require appropriate tagging, including standardized tagging within the 10 OPS threshold framework.
5. **NSE Market Order restriction:** the current NSE FAQ states that algo orders with order type Market Order are not permitted.

Authoritative source references to preserve in the G6 evidence review:

- Angel One SmartAPI exchange regulations: `https://smartapi.angelone.in/exchange-regulations`
- Angel One SmartAPI docs: `https://smartapi.angelone.in/docs/User`
- SEBI Circular `SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/132` dated 2025-09-30.
- NSE Retail Algo FAQ dated 2025-11-03 (`FAQ_Retail Algo_03112025_NSE.pdf`).

Before G6 is closed, these sources must be re-checked for later amendments/superseding documents and the evidence date updated.

## 16. Qualification gates

G6 cannot close unless all of the following have fresh evidence:

1. Phase-5/G5 integration dependency is accepted under the canonical build order.
2. S2 device/session gating dependency required by the root plan is qualified.
3. `check_phase6_live_readonly.py` passes, including unsafe synthetic fixtures.
4. Angel One V2 read-only contract/conformance tests pass.
5. Read-only reconciliation uses `LiveBrokerReconciler` as verdict authority and proves deterministic foreign-activity classification.
6. Foreign activity creates shared `FailureIncident`/alert evidence and halts new-entry eligibility without broker mutation.
7. Disconnect/reconnect/auth-expiry/rate-limit chaos tests pass with no auto-arm.
8. Static-IP/rule-policy eligibility fails closed on missing/stale/unverified evidence.
9. Protective-capability observation is recorded and unknown required capability remains DISARMED.
10. Dated broker/exchange/regulatory review evidence is current for G6 exit.
11. Full regression/golden prior gates remain green.
12. Dual-Windows deterministic G6 fingerprint comparison passes.
13. Live mutation remains structurally unreachable.

If hosted CI runners fail before test provisioning, G6 remains **NOT QUALIFIED**. Infrastructure failure must not be represented as code GREEN or code RED.

## 17. Future mutation boundary

A later phase/release may design a real mutation adapter, but it must be a separate reviewed capability boundary. It must not be enabled by deleting a `read_only` check from the G6 adapter.

The future design must separately address:

- explicit Owner authorization;
- current regulatory/broker re-verification;
- S2/session eligibility;
- RiskGate capability handoff;
- local Live exclusivity;
- broker-resident protective placement/verification;
- idempotency and IN_DOUBT handling;
- mutation-specific rate policies;
- pilot limits and rollback;
- production evidence and release qualification.

Nothing in this Phase-6 design pre-approves that work.
