# AlgoFortis V2 — Phase 2 G2 Evidence

| Field | Value |
|---|---|
| Gate | G2 — Safety Spine |
| Date | 2026-09-23 |
| Branch | `v2-phase2-safety-spine` |
| Qualification candidate | `205533e242887bb66ebf6efff9a13e2126140e9c` |
| Workflow | `V2 Phase 2 Safety Spine Verification` |
| Qualification run | Run #68 — GitHub Actions run `35828220188` |
| Result | **PASS** |
| Live safety state | **READ_ONLY / DISARMED; zero real broker mutation introduced by Phase 2** |

---

## 1. G2 exit criteria

The Phase 2 Safety Spine plan requires a single testable path from `OrderIntent` through the central Risk Gate to an opaque `ApprovedOrder`, plus focused CI evidence for INV-01, INV-02, INV-03, INV-05, INV-06, INV-07, INV-08, INV-11, INV-15, INV-16 and INV-17. The qualification candidate above was checked out by exact SHA and tested on two clean Windows environments with Python 3.13.14.

| G2 criterion | Evidence | Status |
|---|---|---|
| Phase 2 static safety policy is enforced | `build/tools/check_phase2_safety_spine.py` passed on both environments. It verifies required Safety Spine authorities/tests exist, safety-domain modules do not import concrete live broker adapters, and frozen kill-switch/no-auto-arm markers remain present. | **PASS** |
| INV-01 — no duplicate executable order identity | Deterministic `client_order_id` derivation plus `IntentGuard` tests reject duplicate intent IDs, duplicate client-order IDs and restart-restored replays. | **PASS** |
| INV-02 — no stale restart/replay execution | Risk Gate checks `valid_until`; `IntentGuard` rechecks expiry before consumption; stale capabilities are rejected without consuming identity. | **PASS** |
| INV-03 — no executable order without the central gate | Direct `ApprovedOrder(...)` construction is rejected; the opaque capability can be minted only through the Risk Gate authority after successful risk and audit evidence. | **PASS** |
| INV-05 — backtest cannot reach live mutation | Mode-isolation tests and the independent module-boundary gate prevent backtest paths from loading live mutation implementations. | **PASS** |
| INV-06 — paper cannot reach live broker mutation | Broker-neutral port/conformance tests reject run-mode mismatch and keep paper construction isolated from real broker credentials/mutation adapters. | **PASS** |
| INV-07 — lifecycle/live transitions are valid only | Order lifecycle and live-state-machine suites enumerate legal transitions and reject representative illegal transitions. | **PASS** |
| INV-08 — IN_DOUBT is never blindly retried | Lifecycle tests require broker-truth resolution before transition/retry; NOT_FOUND retry preserves identity and requires unexpired intent plus re-approval. | **PASS** |
| INV-11 — hard-limit hierarchy cannot be widened downstream | Decimal-safe `HardLimitHierarchy` tests enforce platform → owner → user → strategy → run monotonic restriction and deterministic resolved snapshot identity. | **PASS** |
| INV-15 — live never auto-arms | Live armed latch defaults false; restart/crash/reconnect recovery cannot enter ACTIVE automatically; ACTIVE requires explicit arm authority, while Phase 2 keeps live DISARMED. | **PASS** |
| INV-16 — trading-critical audit failure is fail-closed | Risk approval, live state transition and Emergency Stop tests inject audit failure and prove the protected state/capability mutation does not occur. | **PASS** |
| INV-17 — options remain BUY-only at the gate | Central Risk Gate rejects option entry sides other than BUY before evaluator approval. | **PASS** |
| Emergency Stop semantics match ADR-010 | Standard Emergency Stop is `HALT_ENTRIES + CANCEL_PENDING` for pending entry orders only; protective exits and reconciliation remain active; `FLATTEN_ALL` is a distinct explicit action and is never implied. | **PASS** |
| Dual-Windows full regression remains green | Both environments passed 51 focused Phase 2 tests and the 302-test full suite. | **PASS** |
| Existing architecture regression remains green | `build/tools/run_regression_certification.py`: 13/13 tests passed on both environments. | **PASS** |
| Deterministic golden evidence remains unchanged | Phase 0 market-data and runtime-configuration fingerprints matched their frozen values on both environments. | **PASS** |

---

## 2. Qualification environments

### Environment A

- GitHub hosted Windows latest runner
- Windows Server 2025 Datacenter, build 26100
- Python 3.13.14
- Exact candidate checkout: `205533e242887bb66ebf6efff9a13e2126140e9c`
- Module-boundary gate: PASS
- Compile gate: PASS
- Phase 1 foundation static policy: PASS
- Phase 1 focused suite: **41 passed**
- Phase 2 Safety Spine static policy: PASS
- Phase 2 focused invariant suite: **51 passed**
- Full suite: **302 passed, 1 warning**
- Architecture regression certification: **13/13 PASS**
- Golden fingerprints: PASS

### Environment B

- GitHub hosted Windows 2022 runner
- Windows Server 2022 Datacenter, build 20348
- Python 3.13.14
- Exact candidate checkout: `205533e242887bb66ebf6efff9a13e2126140e9c`
- Module-boundary gate: PASS
- Compile gate: PASS
- Phase 1 foundation static policy: PASS
- Phase 1 focused suite: **41 passed**
- Phase 2 Safety Spine static policy: PASS
- Phase 2 focused invariant suite: **51 passed**
- Full suite: **302 passed, 1 warning**
- Architecture regression certification: **13/13 PASS**
- Golden fingerprints: PASS

The one full-suite warning is the existing Starlette `anyio.abc.BlockingPortal` deprecation warning. It is non-blocking and not a Phase 2 safety failure.

---

## 3. Deterministic golden fingerprints

Both qualification environments reproduced the frozen values:

- Market data fingerprint: `7620420d3bbe9c3dc805947f86d31e64ec6214f43441edc2844ded1f112e0c35`
- Runtime configuration fingerprint: `6e9168409c73254f8d38ff92025929ed6ebfa104d5150696fdc75ac03efef616`

No golden drift was observed.

---

## 4. Phase 2 task ledger

| Task | Delivered Safety Spine component | Qualification state |
|---|---|---|
| Task 1 | Canonical `OrderIntent` / `RiskDecision` / opaque `ApprovedOrder` capability and central `RiskGateV2` authority | **VERIFIED** |
| Task 2 | Decimal-safe hard-limit hierarchy, resolved snapshot binding and options BUY-only gate | **VERIFIED** |
| Task 3 | Duplicate/stale intent suppression with restart-restorable consumed identity | **VERIFIED** |
| Task 4 | Versioned order lifecycle with `IN_DOUBT`, broker-truth resolution and no blind retry | **VERIFIED** |
| Task 5 | Mode isolation, broker-neutral port and paper conformance shell | **VERIFIED** |
| Task 6 | Live state machine and never-auto-arm latch with audit-before-state transitions | **VERIFIED** |
| Task 7 | ADR-010 Emergency Stop / reconciliation-mismatch domain contract and audit fail-closed entry halt | **VERIFIED** |
| Task 8 | Dedicated Phase 2 static/invariant CI gates and G2 evidence | **PASS — this document** |

---

## 5. Safety and governance checks

- OD-V2-07 is FROZEN by ADR-010.
- Standard Emergency Stop is `HALT_ENTRIES + CANCEL_PENDING` for pending entry orders; protective exits and reconciliation remain active.
- `FLATTEN_ALL` is separate and explicit and is not automatically triggered by Emergency Stop or reconciliation mismatch.
- `ApprovedOrder` remains an opaque capability issued by the central Risk Gate only.
- Hard limits are monotonic and cannot be widened by lower-precedence layers.
- Backtest and paper remain structurally isolated from live broker mutation implementations.
- Restart, crash and reconnect paths do not auto-arm live.
- Audit-required trading-critical actions fail closed.
- Options entry remains BUY-only at the central gate.
- Phase 2 introduced no real broker mutation path and does not authorize real-money live execution.

---

## 6. G2 qualification verdict

**Qualification candidate: PASS.**

Run #68 proves all authoritative Phase 2 gates green on both clean Windows environments at candidate `205533e242887bb66ebf6efff9a13e2126140e9c`. The final Phase 2 closure condition is a fresh exact-head dual-Windows GREEN run on the commit containing this evidence document itself.

This gate qualifies the Phase 2 Safety Spine only. It does not arm live trading, enable real broker mutation, or authorize any live-money execution path.
