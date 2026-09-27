# AlgoFortis V2 Convergence + V1 Salvage Design

**Date:** 2026-09-28  
**Status:** Design for owner review  
**Working branch:** `v2-convergence-v1-salvage-20260928`  
**Initial base:** `v2-phase6-multibroker-transport-impl` @ `7cdb84f441255568386c488c20610c87198a9f68`

## 1. Purpose

Continue productive development while hosted GitHub Actions Windows capacity/quota is unavailable, without waiting for formal hosted qualification.

The branch will become the isolated convergence and product-integration workspace for:

1. converging the locally completed Phase 5, S2, Phase 6, Phase 7, and Phase 8 work;
2. selectively salvaging valuable capabilities from the complete V1 `AlgoFortis_FINAL` archive;
3. adapting Laya onto the canonical Phase 8 AI boundary;
4. implementing the approved Phase 9 Product + Operations work against the converged V2 base;
5. preparing UI/product design and implementation on the same isolated branch;
6. deferring only formal hosted dual-Windows qualification and final release promotion until hosted runners are available again.

This is not a direct V1-to-V2 Git merge and it is not a big-bang rewrite.

## 2. Success Criteria

The convergence branch is ready for formal qualification when all of the following are true:

- Phase 5, S2, Phase 6, Phase 7, and Phase 8 capabilities coexist in one tree.
- No duplicate authority is introduced for risk, order approval, live execution, identity, paper execution, persistence, incident handling, or audit.
- V1 reusable product/platform capabilities are either preserved, adapted, rewired, or explicitly rejected through a mechanical salvage matrix.
- Phase 9 runtime/product implementation is complete on the converged tree.
- Laya is integrated only as research/routing/market-intelligence capability under the Phase 8 shadow boundary.
- Local/static/deterministic verification available without hosted runners is green.
- Formal hosted qualification remains explicitly pending until Windows runners are available.
- `main` is not updated from this branch until exact-head qualification passes.

## 3. Frozen Safety Invariants

These remain non-negotiable throughout convergence and V1 salvage:

- `RiskGateV2` remains the sole authority that can mint `ApprovedOrder`.
- Live remains `READ_ONLY / DISARMED`.
- No code path may auto-arm Live.
- Backtest, Paper, and Live authority remain isolated.
- AI and Laya remain non-executing advisory/research systems.
- AI/Laya output must never bypass deterministic policy/risk validation.
- Unknown, stale, ambiguous, or conflicting authority fails closed.
- Broker credentials, private keys, and live mutation secrets remain local-only.
- Existing stable V1 semantic contracts are preserved/wrapped/extended rather than rewritten for style.
- No generated V1 tree, cached dependency tree, duplicate worktree, or staged installer output becomes V2 source authority.

## 4. Current Source Heads and Topology

The convergence must use exact known source heads rather than branch-name assumptions.

| Area | Source | Exact head / treatment |
|---|---|---|
| Main canonical merged baseline | `main` | `734df15a733e45ff994258c3f41cead950101335` |
| Phase 5 | `v2-phase5-paper-recovery` | `d7c71d21ff9bda6fa3ee1a3bfacd7b124f2a1241` |
| S2 implementation | `v2-s2-account-device-session` | `fce7bedd9b2f6561324f667bcdd524f73fab3ccb` |
| S2 qualification deltas | `v2-s2-qualification-20260926` | `b95b5c1f5daf9b8ede72f4cd36c31431a7dee7d9` |
| Phase 6 + multi-broker | `v2-phase6-multibroker-transport-impl` | `7cdb84f441255568386c488c20610c87198a9f68` |
| Phase 7 implementation | `v2-phase7-portfolio-risk-impl` | `ec52bfaca337134cfc7298c6abfeaacb79c2879b` |
| Phase 8 implementation | `v2-phase8-ai-shadow-impl` | `acc74317e01bfc3efbef0f4e528011f838787995` |
| Laya legacy integration line | `laya-integration` | `65127819df42cf8376de2c4ec13faccd56d9037a` |
| Phase 9 approved design | `v2-phase9-product-ops-design` | `c5d46381cb7d4d6a306369a2c51ad087b47cfb30` |

Topology findings that control the merge strategy:

- Phase 6 multi-broker already carries the Phase 5/S2 family and is therefore the safest convergence trunk.
- Current Phase 5 is only one commit ahead of the Phase 6 family; that delta is the exact-head local requalification evidence document.
- S2 qualification contains two small deltas not present in the Phase 6 family: the Linux smoke workflow and the updated isolation test.
- Phase 7 is an orthogonal implementation line rooted from the earlier merged base and must be brought into the convergence tree deliberately.
- Phase 8 is another diverged implementation line and must be reconciled after Phase 7.
- Laya was built from the older Phase 4-era AI seam and must be adapted to Phase 8 rather than merged wholesale.

## 5. Selected Integration Architecture

### 5.1 Convergence trunk

The branch begins from Phase 6 multi-broker because it already contains the broadest compatible Phase 5 + S2 + Phase 6 lineage.

Convergence order:

1. Phase 6 multi-broker trunk (already branch base).
2. Phase 5 exact-head evidence delta.
3. S2 qualification-only deltas.
4. Phase 7 portfolio/risk implementation.
5. Phase 8 AI research/shadow implementation.
6. Canonical main-only documentation/decision deltas when they are not already represented by Phase 8.
7. Laya adaptation into the Phase 8 AI boundary.
8. V1 mechanical salvage.
9. Phase 9 Product + Operations implementation.
10. Final local qualification package and hosted qualification preparation.

Integration is performed in small reviewable slices. A conflict is resolved according to authority hierarchy, not according to which file is newer.

### 5.2 Authority hierarchy for conflicts

When two lines modify the same concern, the winner is chosen by contract authority:

1. frozen safety/owner decisions;
2. V2 deterministic domain contracts;
3. newer phase-specific V2 authority;
4. V1 frozen compatible semantics;
5. UI/product presentation;
6. historical/reference-only implementation.

A UI or old V1 implementation may never override a V2 safety or execution contract merely because it has more code or a later file timestamp.

## 6. V1 Salvage Model

The complete `AlgoFortis_FINAL` archive is an immutable donor/reference snapshot, not a branch to merge.

Before importing product code, create a mechanical salvage matrix. Every meaningful V1 file/component receives exactly one classification:

- `ALREADY_V2` — V2 already has equivalent or stronger capability; no runtime import.
- `PORT` — useful capability missing from V2; adapt behind a V2 contract.
- `UI_REWIRE` — preserve product UX but replace data/authority wiring with V2 services/read models.
- `TEST_SALVAGE` — implementation is obsolete but behavior/test scenario remains valuable.
- `REFERENCE_ONLY` — useful evidence/design/history; no runtime import.
- `DROP` — generated, duplicate, unsafe, obsolete, fake-success, or conflicting authority.

### 6.1 High-value V1 salvage targets

Expected high-value areas include:

- Owner and User product dashboards;
- secure-entry and existing WebAuthn UX where compatible with S2;
- runtime availability and fail-closed UI barriers;
- backtest/product workflow screens;
- options workspace and chart/product visualization;
- live-readiness and orders/portfolio presentation;
- backup/restore and disaster-recovery product flows;
- Windows launcher, installer, packaging, path/ACL and update foundations;
- incident/support/report/governance UX;
- broker read-side/restart/idempotency behavior that maps cleanly onto Phase 5/6 contracts;
- V1 test scenarios and regression knowledge.

### 6.2 Explicit V1 exclusions

Do not transplant as V2 authority:

- old RiskGate/order approval authority;
- duplicate Paper engine/coordinator authority;
- old broker mutation/execution path;
- local-only account authority that conflicts with S2;
- SAMPLE/fake-success/fabricated financial presentation paths;
- duplicate persistence stores that conflict with V2 repositories;
- `.kilo/worktrees/*` duplicate repository trees;
- `node_modules`, caches, `__pycache__`, staged runtimes, `build/stage`, generated installers, or other build output;
- visible legacy branding except where an internal frozen schema identifier must remain for compatibility.

## 7. Laya Integration

Laya is retained, but the old branch must not be merged wholesale because it predates the completed Phase 8 AI architecture.

Laya is adapted under the canonical Phase 8 contracts:

- Laya Router: task/model routing only.
- Laya Market Intelligence: market interpretation and opportunity candidates only.
- Laya Strategy Hunter: research-only strategy discovery.
- Laya adapter/model registry: disabled/fail-closed when no approved model is connected.
- Laya output becomes or maps to Phase 8 `TradeCandidate`/research evidence.
- No Laya code can mint `ApprovedOrder`, call broker mutation, arm Live, or bypass the tool/data gateway.

The actual fine-tuned Laya model remains a replaceable adapter and is not required to complete structural integration.

## 8. Phase 9 as Product Reunion Point

Phase 9 runs on the converged V2 tree, not on the older docs-only partial baseline.

Required Phase 9 areas remain:

- Product-Ops backend boundary;
- versioned privacy notices and consent history;
- access/correction/erasure/grievance/nomination request workflows;
- retention, deletion propagation, legal hold, narrowly scoped safety retention;
- privacy incidents reusing existing `FailureIncident` and `AlertDispatcher` authority;
- operational read models;
- backup/restore/rollback drills and separation of local trading backup from central account/privacy backup;
- Owner Product Operations dashboard;
- User Privacy & Requests dashboard;
- deterministic G9 evidence and qualification tooling.

V1 product/UI capabilities should be reused here where they map cleanly, but the frontend remains a client of V2 services/read models and never becomes trading authority.

## 9. Work Allowed While Hosted Windows Qualification Is Unavailable

Development does not stop while hosted runners are unavailable.

Allowed and expected now:

- branch convergence work;
- conflict resolution;
- code review and static architecture checks;
- Python syntax/import checks where executable locally;
- focused/unit tests on available environments;
- deterministic probes that do not claim hosted qualification;
- salvage-matrix construction;
- V1 test conversion;
- Laya adaptation;
- Phase 9 backend implementation;
- Phase 9 frontend/UI design and implementation;
- frontend typecheck/build where a compatible environment is available;
- documentation/evidence preparation;
- qualification workflow preparation.

Not allowed to claim during the quota outage:

- fresh hosted dual-Windows GREEN;
- exact cross-Windows fingerprint equivalence if the runners did not execute;
- final G5/G6/G7/G8/G9 hosted qualification;
- final release qualification.

A runner-provisioning/quota failure is infrastructure evidence, not a code PASS and not a code FAIL.

## 10. Qualification After Hosted Capacity Returns

When hosted Windows execution is available again, qualification is run against one frozen exact convergence head.

Required closure sequence:

1. freeze exact branch SHA;
2. run full Python regression;
3. run V1-derived compatibility regressions;
4. run Phase 5/S2/6/7/8/9 focused suites and architecture guards;
5. run deterministic probes/fingerprint generation;
6. run Windows-latest and Windows Server 2022 qualification and compare fingerprints;
7. run frontend tests/typecheck/build;
8. run restart/recovery and failure-injection checks;
9. run backup/restore/rollback drills;
10. verify installer/fresh-PC path where applicable;
11. produce consolidated evidence bundle;
12. review open P0/P1 issues;
13. only then consider promotion toward `main` and Phase 10 release qualification.

Hosted qualification failures are fixed on the integration branch and re-run against a new exact SHA. Previous GREEN evidence never automatically applies to a changed head.

## 11. Release Boundary

This convergence does not enable real-money trading.

The branch may become a Phase 10 candidate only after all required qualification evidence is green. Promotion to `main`, live pilot, and any future change to Live mutation authority remain separate explicit decisions.

## 12. Deliverables From This Integration Track

The branch should eventually contain:

1. this approved convergence/salvage design;
2. an implementation plan with slice-by-slice exact source heads;
3. a V1 salvage matrix with classification and rationale;
4. convergence commits for Phase 5/S2/6/7/8;
5. Laya-on-Phase-8 adaptation;
6. Phase 9 backend/product implementation;
7. V1 UI/product rewiring work;
8. local verification/evidence records;
9. hosted qualification workflow/evidence once runners return;
10. a final consolidated release-candidate report.

## 13. Non-Goals

This track does not:

- rewrite AlgoFortis from scratch;
- directly merge the raw V1 archive;
- replace V2 authority with older V1 authority;
- redesign strategy/risk economics without a separate approved requirement;
- auto-enable Live or real-money trading;
- treat hosted-runner unavailability as qualification success;
- merge the working branch into `main` before formal qualification.

## 14. Owner-Visible Working Rule

During the hosted-runner outage, the project continues forward on `v2-convergence-v1-salvage-20260928`. The goal is to finish as much convergence, V1 salvage, Laya adaptation, Phase 9, and UI/product work as can be safely developed and locally checked, leaving the hosted dual-Windows qualification and release decision as the final closure step when capacity returns.
