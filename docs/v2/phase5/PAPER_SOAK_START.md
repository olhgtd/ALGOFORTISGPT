# AlgoFortis V2 Phase 5 — Paper Soak Campaign Start

**Status:** STARTED / RUNNING  
**Started:** 2026-09-26  
**Mode:** PAPER ONLY  
**Qualification baseline:** `866fd2438807ceed23c69e76fd538ce1437906d9`  
**Baseline qualification run:** #202 / `36226622525`  
**Completed qualifying trading sessions at start:** 0

## Purpose

This record starts the Phase-5 Paper soak campaign required by the G5 exit definition. It does **not** claim that the longer Paper soak has completed or passed.

The campaign exists to accumulate real Paper-session evidence over subsequent trading sessions while the Phase-5 implementation remains fail-closed and Live remains `READ_ONLY/DISARMED`.

## Starting invariants

At campaign start, the qualification baseline has fresh dual-Windows evidence for:

- Phase-5 static safety boundaries;
- Phase-5 focused Paper/recovery tests;
- deterministic Phase-5 recovery probe;
- full regression and existing regression certification;
- G4 and G5 cross-Windows deterministic comparisons;
- zero duplicate-order marker in the deterministic G5 probe;
- zero stale-replay marker in the deterministic G5 probe;
- manual-resume requirement after recovery;
- Live default `READ_ONLY/DISARMED`.

## Campaign evidence to accumulate

Each qualifying Paper session should preserve or produce reviewable evidence for:

- session start/end and clean/unclean shutdown state;
- reconciliation history;
- restart/recovery incidents;
- protective-integrity checks;
- feed/clock/session-boundary health;
- duplicate-order and stale-replay counters;
- critical alert delivery attempts;
- Paper-vs-backtest drift evidence;
- expiry/session-boundary behavior where applicable;
- resource/host observations needed to inform later hardware policy.

## Longer soak target

The release plan proposes a later qualification target of at least 20 consecutive trading sessions including relevant weekly/monthly expiry exposure plus induced restart/recovery and disconnect cases, with zero unresolved safety mismatches/invariant violations/unexplained duplicate or stale replay/P0-P1 failures.

Those longer-run criteria are **not claimed complete here**. This record only establishes that the campaign lifecycle has started and is running, which is the Phase-5 G5 exit requirement.

## Safety constraints during campaign

- Paper only; no real-money order execution.
- Live remains `READ_ONLY/DISARMED`.
- No automatic promotion to Live.
- No automatic resume after a sticky safety halt/recovery.
- Recovery/reconciliation precedes retry or new entry permission.
- Missing/corrupt policy/state remains fail-closed.
- PR #8 remains draft/open/unmerged until separately authorized.

## Progress state

- Campaign state: `RUNNING`
- Qualifying sessions completed: `0`
- Long soak pass: `NOT YET EVALUATED`
- G5 technical baseline: `READY FOR OWNER REVIEW`
