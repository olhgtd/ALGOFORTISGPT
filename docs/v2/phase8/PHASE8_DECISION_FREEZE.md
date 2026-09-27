# AlgoFortis V2 — Phase 8 AI / Agents Decision Freeze

**Date:** 2026-09-27
**Status:** FROZEN BY OWNER APPROVAL
**Authority:** This dated freeze is the controlling Phase-8 decision record and supersedes any older `OPEN` labels for OD-V2-15 / OD-V2-16 until the consolidated Owner Decision Register is synchronized.

## OD-V2-15 — AI scope and provider set for V2.0

**Decision:** Research + Shadow only for V2.0. Start with one local and one cloud provider behind the common provider abstraction. Committee/ensemble remains deferred T2 scope.

## OD-V2-16 — AI data-sharing rules

**Decision:** Strict provider data allowlists and redaction at the tool/provider gateway. Broker credentials, broker/account identifiers, personal data, raw trade logs, or other disallowed sensitive trading data must not be sent to any AI provider. Cloud-provider use must be auditable and fail closed when data classification or redaction evidence is unavailable.

**Market/instrument data licensing boundary:** Before any market, instrument, dataset-derived, news-derived, or research data leaves the local machine for a cloud AI provider, Phase 8 must verify the authoritative Data V2 provenance/licensing policy permits that external/provider use. Redaction does not make otherwise restricted data exportable. Missing, stale, ambiguous, or prohibitive licensing/provenance evidence blocks the outbound provider call fail-closed. Local-provider processing remains subject to the dataset's own usage policy but does not create cloud egress.

## Standing safety boundary

- AI remains advisory/research/shadow only.
- AI cannot create or mint `ApprovedOrder`.
- AI has no direct broker, Live execution, credential-store, or trading-state mutation authority.
- Any future executable path must still pass deterministic strategy/rules plus the existing central `RiskGateV2`.
- Provider outage, malformed/policy-violating output, or an expired/stale `TradeCandidate` degrades to `NO_TRADE` / `HOLD`, not fallback execution.
- All runtime agent tools are reached through the deny-by-default Tool Gateway with declared scope, rate/budget limits, and per-call audit evidence.
- Cloud data egress is additionally gated by Data V2 provenance/licensing policy; disallowed or unproven external use is blocked.
- Live remains `READ_ONLY / DISARMED`.
