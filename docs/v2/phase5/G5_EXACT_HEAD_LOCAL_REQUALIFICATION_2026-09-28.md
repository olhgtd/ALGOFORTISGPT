# AlgoFortis V2 Phase 5 — Exact-Head Local Requalification

**Date:** 2026-09-28  
**Branch:** `v2-phase5-paper-recovery`  
**Exact head:** `8b2f9849c5cd064d0169ac40601dae6fb62b87fe`  
**Environment:** Windows PowerShell, Python 3.13.14  
**Purpose:** Supplemental exact-head local requalification after the previously approved G5 dual-Windows baseline qualification.

## 1. Exact-head identity

The local checkout was verified before qualification:

- branch: `v2-phase5-paper-recovery`
- commit: `8b2f9849c5cd064d0169ac40601dae6fb62b87fe`
- Python: `3.13.14`

The repository branch head matched the same commit.

## 2. Phase and architecture checks

The exact-head local run passed:

- Python compile gate
- V2 module-boundary policy
- Phase 1 static check
- Phase 2 safety-spine static check
- Phase 3 Data V2 static check
- Phase 4 static check
- Phase 4 focused tests
- Phase 4 deterministic probe
- Phase 5 Paper/recovery static check
- Phase 5 focused tests
- Phase 5 deterministic probe

## 3. Windows path-length diagnosis and recheck

The first full-regression run reported three failures in `tests_v1/test_v2_phase3_historical_store.py` caused by Windows path length (`WinError 206`) under the default pytest temporary directory. The failing paths combined:

- the default Windows temp prefix;
- pytest's generated test directory;
- content-addressed `dataset_id` and `version_id` directories;
- the temporary Parquet publication filename.

No product-code change was made for this environment-only failure.

The temporary root was remapped to a short `T:` drive and pytest was given a short `--basetemp`.

Focused historical-store recheck:

```text
7 passed in 2.32s
```

## 4. Full regression

Exact-head full regression was then executed with the short Windows pytest base temp:

```text
542 passed, 1 warning in 58.69s
```

The single warning was a third-party Starlette/AnyIO deprecation warning and was not a test failure.

## 5. Regression certification

The existing certification command was rerun after the full regression:

```text
=== STARTING REGRESSION VERIFICATION ===
dashboard resolves strictly from the clean repository root
IMPORT_RESOLUTION_PASS

Ran 13 tests
OK

=== REGRESSION VERIFICATION: ALL PASS ===
```

## 6. Result

**Exact-head local qualification: GREEN.**

This supplemental evidence does not replace or weaken the previously recorded G5 dual-Windows qualification baseline. It confirms the current Phase-5 branch head passes the local architecture, Phase-5 focused, deterministic probe, full-regression, and regression-certification gates when pytest uses a Windows path short enough for the content-addressed historical-store fixture.

Safety invariants remain unchanged:

- Live default remains `READ_ONLY/DISARMED`.
- No Phase-5 component receives real-broker mutation authority.
- Recovery/reconciliation precedes retry or new Paper entry.
- Safety halts do not auto-clear.
- Resume after recovery remains explicit/manual.
- Missing or corrupt safety state fails closed.

The longer Paper soak remains a separate release-evidence campaign and is not reclassified by this local requalification.
