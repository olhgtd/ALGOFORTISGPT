# AlgoFortis V2 — Phase 8 AI / Agents Decision Freeze

**Original freeze date:** 2026-09-27  
**Amended:** 2026-10-01  
**Status:** FROZEN BY OWNER APPROVAL — AMENDED 2026-10-01  
**Authority:** This dated freeze, as amended on 2026-10-01, is the controlling Phase-8 AI decision record and supersedes older `OPEN` labels for OD-V2-15 / OD-V2-16 until the consolidated Owner Decision Register is synchronized. The detailed controlling design is `docs/superpowers/specs/2026-10-01-ai-laya-decision-intelligence-architecture.md`.

## OD-V2-15 — AI scope and provider set for V2.0

**Decision:** AlgoFortis supports optional `0..N` AI providers behind the existing provider abstraction plus optional Laya as a first-class Market Intelligence Engine. Deterministic Strategy remains independently operational with zero AI and with Laya disabled. In research/backtest/paper workflows, Laya/AI may review deterministic StrategyCandidates, challenge evidence, produce independent IntelligenceCandidates, and participate in Strategy Hunting. Dynamic multi-AI review is permitted; fixed participant count and blind majority voting are not required. Correlated model/provider lineage must be recorded so repeated/correlated outputs cannot masquerade as independent confirmation.

**Authority reuse:** Existing provider registry/orchestration/scheduler/queue seams are extended rather than replaced. Existing Portfolio authority owns capital/reservations/exposure. Existing `RiskGateV2` remains the sole `ApprovedOrder` authority. Existing S2 `DeviceSessionGate` remains the account/device/session identity authority. Existing Owner/Admin authority owns global configuration.

**Current execution boundary:** This amendment does **not** authorize real-money broker mutation, Live arming, direct AI-to-order execution, or a second risk/order authority. Current Live remains `READ_ONLY / DISARMED`.

## OD-V2-16 — AI data-sharing rules

**Decision:** Strict provider data allowlists and redaction remain mandatory at the tool/provider gateway. Broker credentials, broker/account identifiers, personal data, raw trade logs, or other disallowed sensitive trading data must not be sent to any AI provider. Cloud-provider use must be auditable and fail closed when data classification or redaction evidence is unavailable.

**Market/instrument data licensing boundary:** Before any market, instrument, dataset-derived, news-derived, research, or Strategy-Hunting data leaves the local machine for a cloud/third-party AI provider, AlgoFortis must verify the authoritative Data V2 provenance/licensing policy permits that external/provider use. After-hours Strategy Hunting is not exempt. Redaction does not make otherwise restricted data exportable. Missing, stale, ambiguous, or prohibitive licensing/provenance evidence blocks the outbound provider call fail closed. Local-provider processing remains subject to the dataset's own usage policy but does not create cloud egress.

## Monitoring and scheduling freeze

- AI/Laya cannot choose their own monitoring scope or cadence.
- Monitoring originates from a versioned Owner-controlled MarketWatchPolicy built by extending the existing `MonitoringPolicyV2` / `MonitoringSchedulerV2` seam.
- AI/Laya may submit a `ScopeExpansionRequest`; only Owner/Admin policy approval may widen scope.
- Provider concurrency/rate-limit/quota pressure is handled through the existing provider-queue seam; expired market tasks are not executed as fresh work.

## Standing safety and authority boundary

- Deterministic Strategy remains operational with AI/Laya unavailable or disabled.
- AI/Laya independent candidates are research/backtest/paper candidate evidence, never `ApprovedOrder` capabilities.
- AI cannot create or mint `ApprovedOrder`.
- AI has no direct broker, Live execution, credential-store, or trading-state mutation authority.
- Existing `RiskGateV2` remains the sole `ApprovedOrder` authority.
- Existing Portfolio/accounting authority remains the single capital/reservation/exposure truth; no AI-specific accounting ledger is permitted.
- Same broker/account capital reservations must be atomic; separate broker/accounts use separate reservation pools while aggregate exposure remains under existing Portfolio authority.
- Provider outage, malformed/policy-violating output, or expired/stale intelligence work degrades the intelligence path; it does not silently break deterministic Strategy processing.
- All runtime agent tools are reached through the deny-by-default Tool Gateway with declared scope, rate/budget limits, and per-call audit evidence.
- Cloud data egress is additionally gated by Data V2 provenance/licensing policy; disallowed or unproven external use is blocked.
- User intelligence entitlements must sit on top of existing S2 `DeviceSessionGate` account/device/session identity authority; no parallel AI authentication mechanism is permitted.
- Global AI/Laya configuration belongs inside the existing authoritative Owner/Admin Dashboard, not a second admin surface.
- Live remains `READ_ONLY / DISARMED`.

## Detailed architecture

The complete locked architecture, invariants, multi-broker capital-pool rule, provider queue behavior, correlated-model evidence, entitlement design and implementation decomposition are controlled by:

`docs/superpowers/specs/2026-10-01-ai-laya-decision-intelligence-architecture.md`
