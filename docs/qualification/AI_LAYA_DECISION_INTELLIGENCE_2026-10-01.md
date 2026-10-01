# AlgoFortis AI/Laya Decision Intelligence Qualification Manifest

**Architecture freeze:** `docs/superpowers/specs/2026-10-01-ai-laya-decision-intelligence-architecture.md`  
**Implementation plan:** `docs/superpowers/plans/2026-10-01-ai-laya-decision-intelligence-implementation.md`  
**Qualification workflow:** `.github/workflows/ai-decision-intelligence.yml`  
**Deterministic probe:** `build/tools/ai_decision_intelligence_probe.py`  
**Status rule:** this implementation is qualified only when the exact PR head completes the named qualification workflow successfully. A successful older/stale head is not sufficient.

## Evidence contract

The qualification workflow checks out `github.event.pull_request.head.sha` explicitly and records that SHA in both Windows evidence artifacts. It requires deterministic evidence on both `windows-latest` and `windows-2022`, then compares the evidence byte-for-byte after CRLF normalization.

Required deterministic markers are:

- `AI_INTELLIGENCE_STRATEGY_INDEPENDENCE=PASS`
- `AI_INTELLIGENCE_ZERO_TO_N=PASS`
- `AI_INTELLIGENCE_CORRELATED_MODEL_FLAG=PASS`
- `AI_INTELLIGENCE_MARKET_WATCH_POLICY=PASS`
- `AI_INTELLIGENCE_PROVIDER_QUEUE=PASS`
- `AI_INTELLIGENCE_RISKGATE_AUTHORITY=PASS`
- `AI_INTELLIGENCE_MULTI_BROKER_RESERVATION=PASS`
- `AI_INTELLIGENCE_OD16_EGRESS=PASS`
- `AI_INTELLIGENCE_S2_ENTITLEMENTS=PASS`
- `AI_INTELLIGENCE_OWNER_DASHBOARD=PASS`
- `LIVE_STATE=READ_ONLY/DISARMED`

The final compare job additionally emits:

- `AI_INTELLIGENCE_CROSS_WINDOWS_COMPARE=PASS`
- `AI_INTELLIGENCE_FULL_REPOSITORY_PRESERVATION=PASS`
- `AI_INTELLIGENCE_DASHBOARD_QUALIFICATION=PASS`

## Required verification surfaces

The exact-head workflow must preserve all of the following:

1. AI/Laya feature tests, including zero/one/many-provider behavior, correlated-model evidence, MarketWatchPolicy, queue/rate-limit behavior, Strategy Hunting licensing, multi-broker candidate reservations, S2-backed entitlements, and Owner-only controls.
2. Existing static authority guards, including `RiskGateV2` as sole `ApprovedOrder` authority, existing Portfolio/accounting truth, S2 identity authority, existing Owner/Admin authority, and Live `READ_ONLY/DISARMED`.
3. Full `tests_v1` Python regression and existing regression certification.
4. Existing Phase 4–9 and S2 deterministic probes.
5. Root and dashboard dependency audits at the existing high-severity gate.
6. Dashboard Vitest suite, TypeScript typecheck, and production Vite build.

## Authority/result boundaries

This qualification does **not** authorize real-money broker mutation or Live arming. The implemented decision-intelligence system is limited to research, backtest and paper workflows. Laya/AI may review deterministic strategy candidates and may emit independent `IntelligenceCandidate` research/paper evidence, but cannot mint `ApprovedOrder`, bypass existing Portfolio authority, bypass `RiskGateV2`, self-expand monitoring scope, self-grant entitlements, or bypass OD-V2-16 external-data licensing/provenance controls.

User-facing AI/Laya product UX remains intentionally deferred. System-wide AI/Laya configuration and entitlement assignment are exposed only inside the existing authoritative Owner/Admin control surface.

## Implementation reference map

- Candidate/council contracts: `engine/ai/v2/contracts.py`, `engine/ai/v2/review_council.py`
- Strategy review/independent candidate orchestration: `engine/ai/v2/orchestrator.py`
- Market watch policy/scheduler: `engine/ai/monitoring_scheduler_v2.py`
- Provider queue/rate-limit policy: `engine/ai/provider_queue_v2.py`
- Scope expansion request: `engine/ai/scope_expansion_v2.py`
- Strategy Hunting + OD-V2-16 egress: `engine/ai/v2/strategy_hunting.py`, `engine/ai/v2/provider_gateway.py`
- Existing-Portfolio candidate arbitration: `engine/portfolio/candidate_arbitration_v2.py`
- Reservation hand-off to existing RiskGate admission: `engine/risk/portfolio_admission_v2.py`
- S2-backed user intelligence entitlements: `dashboard/backend/account_v2/intelligence_entitlements.py`
- Owner/Admin backend controls: `dashboard/backend/owner_admin/decision_intelligence_router.py`
- Existing Owner AI Control Center extension: `dashboard/owner-dashboard/authoritative/DecisionIntelligenceControls.tsx`, `dashboard/owner-dashboard/authoritative/AIControlCenter.tsx`
- Static authority guard: `build/tools/check_ai_decision_intelligence_boundary.py`

No merge or release decision is implied by this manifest; merge consideration requires a successful exact-head workflow and separate repository review policy.
