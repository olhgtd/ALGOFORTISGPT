# ADR-014 — Phase 5 Independent Alert Channel Policy

- **Date:** 2026-09-25
- **Status:** ACCEPTED / OWNER-FROZEN
- **Decision:** OD-V2-19
- **Phase:** AlgoFortis V2 Phase 5 — Paper V2, Reconciliation & Recovery

## Context

Phase 5 requires critical operational alerts to remain observable even when one delivery mechanism fails. The V2 requirements require at least two independent channels for critical alerts and the G5 gate requires an alert-channel-independence test.

## Decision

1. Critical Phase-5 alerts MUST be attempted through at least two independent delivery paths:
   - a local on-screen / Windows-visible alert path; and
   - Telegram as the external remote alert path.
2. Email is an optional third adapter and is not required for the Phase-5 gate.
3. Delivery adapters share a versioned alert contract, but delivery attempts are independent. Failure of one channel MUST NOT suppress or short-circuit attempts on the other required channel.
4. Critical alert payloads are minimal and redacted. They MUST NOT include broker credentials, secrets, raw account identifiers, authentication tokens, or unrestricted trade logs.
5. Alert delivery failure is itself auditable and observable. A failed channel is recorded without turning a successfully delivered independent channel into a failure.
6. Paper safety logic MUST NOT depend on Telegram availability. Telegram outage cannot loosen RiskGate, reconciliation, recovery, stale-data, or kill-switch behavior.
7. A remote "engine silent" / dead-PC heartbeat is DEFERRED from this decision because it would cross into telemetry/privacy policy governed by OD-V2-22. Phase 5 keeps a clean adapter seam for that future capability.
8. This decision does not authorize cloud trading, broker mutation, or remote arming.

## Required Phase-5 verification

- Unit/contract tests for alert envelope validation and redaction.
- Failure-injection test: local channel fails while Telegram is attempted.
- Failure-injection test: Telegram fails while local channel is attempted.
- Test proving one channel failure cannot suppress the second channel.
- Test proving notifier failures cannot bypass or weaken paper/recovery safety state.
- Evidence is included in G5 qualification.

## Safety invariants preserved

- Live remains `READ_ONLY` / `DISARMED`.
- No notifier may place orders, arm engines, mutate RiskGate policy, or alter reconciliation verdicts.
- Secrets remain local and excluded from alert payloads.

## Consequence

OD-V2-19 is FROZEN for Phase 5. Any future heartbeat/central-service liveness mechanism requires a separate decision under telemetry/privacy governance.