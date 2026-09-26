# AlgoFortis V2 — G6 Evidence

**Status:** NOT QUALIFIED  
**Evidence date:** 2026-09-27  
**Phase:** Phase 6 — Live Execution V2 (READ_ONLY / DISARMED)  
**Implementation branch:** `v2-phase6-live-readonly-impl`  
**Implementation head before evidence documents:** `90a18365eb5c7824aaaa38add04a5b7710018600`

## Binding interpretation

`G6 GREEN` does **not** enable real-money trading. Live remains `READ_ONLY / DISARMED` unless a later separately designed, reviewed, qualified, and explicitly authorized release gate changes that state.

This record does not contain credentials, tokens, account identifiers, or any broker-mutation authorization.

## Implemented evidence surfaces

The Phase-6 branch contains:

- isolated `engine/broker_adapters/angelone_v2/` boundary;
- read-only contracts and explicit injected broker profile/endpoints;
- fail-closed session lifecycle with redacted errors and no fake-success transport fallback;
- versioned rate/compliance/order/protection policy seams with no guessed production defaults;
- read-only broker truth adapter with no callable place/submit/modify/cancel/GTT methods;
- read-only broker conformance kit;
- existing `engine/reconciliation/live_reconciler.py` retained as verdict authority and hardened so full reconciliation cannot convert unavailable broker truth into an empty-clean result;
- Phase-5 `FailureIncident` and alert vocabulary reused for foreign order/position and broker-truth uncertainty;
- deterministic incident IDs and `record_once(...)` boundary to bound repeated alerts;
- structural static guard `build/tools/check_phase6_live_readonly.py` independent of runtime flags;
- deterministic G6 evidence/probe;
- dedicated dual-Windows G6 workflow with exact cross-Windows fingerprint comparison.

## Local focused verification

A local isolated Phase-6 workspace was used for RED → GREEN focused development because hosted GitHub runners were not provisioning job steps during the session.

Latest focused local result before these evidence documents:

- Phase-6 focused tests: `56 passed`;
- structural mutation firewall: `PASS`;
- deterministic probe fingerprint: `8a17086ea4eb3c8cc3e55b8b539019ae2f0f10ed504abb7dd59016c24b75c45d`;
- probe markers include:
  - `BROKER_BOUNDARY=V2_ISOLATED_READ_ONLY`
  - `RECONCILIATION_AUTHORITY=LIVE_RECONCILER`
  - `FOREIGN_ACTIVITY_INCIDENT_MODEL=PHASE5_SHARED`
  - `LIVE_STATE=READ_ONLY/DISARMED`
  - `REAL_BROKER_MUTATION_CAPABILITY=ABSENT`
  - `G6_ENABLES_REAL_MONEY_TRADING=NO`

This focused result is **not** a substitute for full-repository regression, Windows qualification, or real broker read-only evidence.

## Dated rule review re-check

Public engineering inputs were re-checked on 2026-09-27 immediately before preparing this evidence record.

- Angel One SmartAPI Exchange Regulations still state that API order execution requires the registered Static IP effective 2026-04-01.
- Current SmartAPI documentation uses the `apiconnect.angelone.in` API host for documented endpoints.
- Angel One's official SmartAPI compliance communication records a combined order-request cap of 9 requests/second; this remains external versioned evidence and is not embedded as a production source constant.
- NSE Retail Algo FAQ `FAQ_Retail Algo_03112025_NSE.pdf` states that API client orders are considered algo orders, describes the 10 OPS tagging framework, and states that algo Market Orders are not permitted.
- SEBI Circular `SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/132` records that the retail-algo framework is applicable to all stock brokers from 2026-04-01.

These are engineering/compliance inputs, not legal advice and not execution authorization. They must be re-checked again before any future mutation/pilot gate.

## Evidence still required before G6 can be QUALIFIED

G6 remains `NOT QUALIFIED` until all of the following are evidenced on the exact qualification head:

1. Hosted/approved Windows jobs actually execute the focused/static qualification instead of failing before step provisioning.
2. Both Windows legs produce byte-identical G6 evidence and the compare job passes.
3. Full repository regression/golden and stacked G4/G5/GP-S2 preservation gates execute successfully.
4. S2 dependency is qualified as required by the canonical phase plan.
5. An authorized observation-only Angel One session supplies redacted orders/positions/funds health evidence for the number of sessions required by a frozen qualification policy; no session count is invented here.
6. Disconnect/reconnect, expiry, and rate-limit evidence is captured without broker mutation.
7. Foreign-activity evidence is shown flowing through `LiveBrokerReconciler` into the shared incident/alert path.
8. Exact workflow/run IDs, artifact fingerprints, rule-review date, and unresolved limitations are archived.

## Explicit blockers at this evidence snapshot

- No real-account read-only session evidence is recorded in this repository snapshot.
- No completed dual-Windows G6 compare is recorded in this repository snapshot.
- Hosted Actions had repeatedly failed before executing job steps during preceding Phase-5/S2 verification attempts; therefore no current-head CI GREEN is inferred.
- No broker mutation test or real-money order is required or authorized for G6 read-only qualification.

**Result: G6 = NOT QUALIFIED. Live = READ_ONLY / DISARMED.**
