# AlgoFortis V2 — Phase 8 AI / Agents Decision Freeze

**Date:** 2026-09-27
**Status:** FROZEN BY OWNER APPROVAL

## OD-V2-15 — AI scope and provider set for V2.0

**Decision:** Research + Shadow only for V2.0. Start with one local and one cloud provider behind the common provider abstraction. Committee/ensemble remains deferred T2 scope.

## OD-V2-16 — AI data-sharing rules

**Decision:** Strict provider data allowlists and redaction at the tool/provider gateway. Broker credentials, broker/account identifiers, personal data, raw trade logs, or other disallowed sensitive trading data must not be sent to any AI provider. Cloud-provider use must be auditable and fail closed when data classification or redaction evidence is unavailable.

## Standing safety boundary

- AI remains advisory/research/shadow only.
- AI cannot create or mint `ApprovedOrder`.
- AI has no direct broker, Live execution, credential-store, or trading-state mutation authority.
- Any future executable path must still pass deterministic strategy/rules plus the existing central `RiskGateV2`.
- Provider outage or malformed/policy-violating output degrades to `NO_TRADE` / `HOLD`, not fallback execution.
- Live remains `READ_ONLY / DISARMED`.
