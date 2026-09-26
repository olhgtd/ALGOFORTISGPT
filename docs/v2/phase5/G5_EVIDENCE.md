# AlgoFortis V2 Phase 5 — G5 Evidence

**Status:** TECHNICAL EXIT EVIDENCE READY — OWNER GATE APPROVED 2026-09-26  
**Date:** 2026-09-26  
**Qualification baseline commit:** `866fd2438807ceed23c69e76fd538ce1437906d9`  
**Qualification workflow:** `V2 Phase 5 Paper Recovery Qualification`  
**Qualification run:** #202 / `36226622525`  
**Branch:** `v2-phase5-paper-recovery`  
**PR:** #8 — draft, open, unmerged

## 1. G5 exit criteria

Canonical Phase-5 exit requires:

1. restart/recovery with open Paper state without duplicate orders or stale replay;
2. required Paper failure-injection catalogue green;
3. deterministic recovery/evidence qualification green;
4. Paper soak campaign started and running;
5. prior regression/golden behavior preserved;
6. Live remains fail-closed and DISARMED.

The technical evidence below satisfies items 1–3, 5 and 6 at the qualification baseline. The Paper soak campaign is recorded separately in `docs/v2/phase5/PAPER_SOAK_START.md` as **STARTED / RUNNING**, not completed. The Owner gate approval is recorded in `docs/v2/phase5/G5_OWNER_APPROVAL.md`.

## 2. Exact-head dual-Windows qualification

Run #202 / `36226622525` checked out exact head `866fd2438807ceed23c69e76fd538ce1437906d9`.

### Windows latest / Python 3.13.14

- V2 module-boundary policy: PASS
- compile gate: PASS
- Phase 1 static + focused: PASS
- Phase 2 safety-spine static + focused: PASS
- Phase 3 Data V2 static + focused: PASS
- Phase 4 static + focused + deterministic probe: PASS
- Phase 5 static Paper/recovery policy: PASS
- Phase 5 focused validation: PASS
- Phase 5 deterministic probe: PASS
- full `tests_v1` regression: PASS
- existing regression certification: PASS
- Phase 0 deterministic golden probe: PASS

### Windows 2022 / Python 3.13.14

The same gate sequence above: PASS.

### Cross-Windows deterministic comparisons

- G4 deterministic fingerprint comparison: PASS
- G5 deterministic fingerprint comparison: PASS

The G5 comparison requires identical Phase-5 output across both Windows runners and explicitly checks:

- `FINAL_STATE=READY_FOR_RESUME`
- `MANUAL_RESUME_REQUIRED=true`
- `DUPLICATE_ORDER_COUNT=0`
- `STALE_REPLAY_COUNT=0`
- `DEFAULT_LIVE_STATE=READ_ONLY/DISARMED`

## 3. Phase-5 implementation evidence

### P5-01 — Contracts + operational state

Canonical Paper states are locked to:

- `HEALTHY`
- `DEGRADED`
- `HALTED`
- `RECOVERY`
- `READY_FOR_RESUME`

`HALT_ENTRIES` is an action; `HALTED` is the sticky resulting state. Safety recovery never auto-resumes Paper entry permission. `READY_FOR_RESUME` requires explicit manual resume.

### P5-02 — Deterministic Paper fill simulation

Paper execution uses RiskGate-approved Paper capabilities only, conservative bid/ask execution semantics, deterministic slippage/latency/rejection/disconnect simulation, and fail-closed quote validation. No real-broker mutation path is introduced.

### P5-03 — Persistence + checkpointing

Additive V8 persistence records Paper sessions, orders, positions, checkpoints, incidents, alert evidence, and recovery reports.

Checkpoint/owned-state restoration fails closed when referenced order or position state is missing; missing owned truth is never silently skipped.

### P5-04 — Reconciliation + recovery

Recovery ordering is enforced as restore → reconcile → protective integrity → health/session gates. Non-CLEAN or uncertain reconciliation blocks new entries. Recovery has no order-submit/retry authority.

### P5-05 — Protective integrity + session/expiry

Protective-state integrity is independent from reconciliation. CLEAN reconciliation cannot bypass missing/invalid protective state. Expiry/session handling is explicit and fail-closed; no invented automatic flatten or silent carry is permitted.

### P5-06 — Versioned failure/storm policy

Storm thresholds are injected/versioned rather than guessed production constants. Cooldown/reset semantics are enforced. Missing/invalid policy does not create unlimited retry permission.

### P5-07 — Host resilience

Host policy covers single-instance ownership, sleep/resume recovery semantics, clock-health preflight, temporary session power policy, and watchdog recovery-only behavior. Phase-5 CI uses injectable/test seams rather than modifying runner power plans or clocks.

### P5-08 — Independent critical alerts

Critical alerts fan out independently to local Windows-visible and Telegram adapter seams. Failure in one adapter cannot suppress the other. Payload redaction removes credentials/tokens/raw account identifiers/unrestricted trade logs. Alert delivery cannot arm Live or mutate trading authority.

### P5-09 — Drift + evidence

Paper-vs-backtest drift reporting is deterministic and explanatory only. It does not grant strategy promotion. Missing drift policy fails closed. Recovery/G5 evidence fingerprints are deterministic.

### P5-10 — Failure injection + qualification + runtime wiring

The required deterministic Paper safety-fixture catalogue covers:

`FI-01`, `FI-02`, `FI-03`, `FI-04`, `FI-05`, `FI-06`, `FI-07`, `FI-08`, `FI-09`, `FI-12`, `FI-13`, `FI-14`, `FI-23`, `FI-24`.

Fixture assertions include zero duplicate submission, zero stale replay, no unresolved passing-case mismatch, no Live arm permission, reconciliation-before-resume, protective integrity, manual resume, rollover invalidation, and independent alert attempts.

**Scope note:** these are deterministic safety/failure fixtures and adapter-level fault simulations. This evidence does not claim that CI physically crashes a production PC, alters the Windows clock, disconnects real networking, fills a real disk, or contacts a real broker.

Operational Paper runtime wiring is provided by `engine/paper/phase5_runtime_v2.py`, which wraps the existing Paper runner rather than rewriting the large legacy runner. It enforces:

- second-instance fail-closed before delegate initialization;
- clock-health entry preflight;
- temporary active-session sleep prevention boundary;
- sleep/resume → recovery;
- recovery success → `READY_FOR_RESUME`, never automatic Paper resume;
- explicit `manual_resume()` before delegate run;
- host lock/power cleanup on shutdown/failure;
- no `arm`, `place_order`, or `submit_order` capability.

The Phase-5 static checker pins this runtime wrapper and its focused tests so deletion/bypass becomes a CI failure.

## 4. TDD evidence highlights

Important RED → GREEN checkpoints include:

- P5-03 persistence hardening: RED `d4e623195084166d14cb065e79b299bc7be467d9` → GREEN `690e16902c6cf39ca6a35c469ec048993e30d775`.
- P5-08 alerts: RED `4894b05c9eadf817bb6e7038d150823754dd4af5` → GREEN `72bdbb4ab65775c2d84d1a36cdd750cbb5a89d0e`.
- P5-09 drift/evidence: RED `73a6af5b2ddd34f55f90581a9810c102d73cef46` → GREEN `9559e3d68ce19d262a28335d21d105f6decac33e`.
- P5-10 FI catalogue: RED run #194 on `c7c5c6dfc330664d02ebc2a7aa4bf289c731ed02` established the missing FI authority before implementation.
- Phase-5 operational runtime wiring: RED `3214b0d028e7012c69781d6fc74c64bb5c0df798` → GREEN `b78318a0fc3015be499dd0d711f22c66f075e93e`.
- Static runtime-wiring pin: RED `174b3ddf297be6150ac9a2d1b1c2fbee2fd2a2bc` → GREEN baseline `866fd2438807ceed23c69e76fd538ce1437906d9`.

## 5. Safety invariants at G5 baseline

- Live default remains `READ_ONLY/DISARMED`.
- No Phase-5 Paper component owns a real-broker mutation capability.
- Recovery/reconciliation has precedence over retry/new entries.
- Safety halts do not auto-clear.
- Resume after recovery is explicit/manual.
- Missing/corrupt safety state or policy fails closed.
- No guessed production storm, clock-drift, drift-tolerance, promotion, or hardware thresholds were frozen in Phase 5.

## 6. Governance state after Owner approval

The Owner explicitly approved the G5 gate on 2026-09-26; see `docs/v2/phase5/G5_OWNER_APPROVAL.md`.

The following remain separate from G5 Owner approval:

- PR #8 remains draft/open/unmerged until a separate explicit merge decision;
- the proposed longer Paper soak continues and is not claimed passed;
- Live remains `READ_ONLY/DISARMED`;
- G5 approval does not authorize real-money trading;
- Phase 6 remains subject to its frozen decisions, S2 dependency, design/implementation gates, and DISARMED qualification requirements.
