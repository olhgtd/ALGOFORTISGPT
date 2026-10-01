# AlgoFortis Live Reunion Plan Amendment — Account Domains + AI Provider Queue

**Status:** Normative amendment to `docs/superpowers/plans/2026-09-30-v1-v2-live-reunion-implementation.md`  
**Date:** 2026-10-01  
**Branch:** `live-v1-v2-reunion-20260930`  
**Safety:** Live remains `READ_ONLY / DISARMED`; AI remains advisory-only with no broker mutation authority.

This amendment records two reviewed requirements that are binding for the implementation plan and final qualification.

## A. Broker-account capital domains are independent

### Binding rule

The capital/exposure arbitration domain is the exact broker-account identity:

`AccountCapitalDomainKey = (broker_id, broker_account_ref)`

Candidates that share the same `AccountCapitalDomainKey` compete for the same atomic capital/exposure pool. Candidates belonging to different domain keys do not consume or reserve each other's capital and may be evaluated by independent Account Arbiter instances in parallel.

A shared persistence backend is allowed to serialize short database write transactions internally for integrity, but this must not create logical capital coupling between different broker accounts.

### Same-account rule

For simultaneous candidates on one account (for example BANKNIFTY CE, NIFTY CE, SENSEX PE):

1. deterministic hard eligibility,
2. current portfolio/correlated exposure impact,
3. owner-configured strategy priority,
4. deterministic pre-AI strategy edge/quality evidence,
5. deterministic capital-efficiency evidence,
6. signal/event timestamp,
7. stable candidate identity as final tie-break,

must produce a stable ordering before atomic reservations are committed. Pending/unfilled orders remain part of reserved capital/exposure until an explicit terminal/reconciliation release.

No thread arrival order, provider timing, AI response timing, or OS scheduling may decide which candidate wins limited shared capital.

### Required implementation correction

The V9 execution-capacity model currently scopes reservations by `broker_account_ref`. Before Package-1 qualification it must be hardened so every capacity reservation and aggregate query includes both `broker_id` and `broker_account_ref`.

Required changes include:

- `LiveExecutionCapacityEvidence` carries `broker_id` plus `broker_account_ref`.
- `LiveExecutionCapacityReservation` carries `broker_id` plus `broker_account_ref`.
- V9 reservation rows use `(broker_id, broker_account_ref)` as the account-capital domain.
- active reserved cash/exposure queries are scoped by both fields.
- global `client_order_id` uniqueness remains independent of account-domain identity.
- tests prove two different broker-account domains can reserve independently while simultaneous candidates in one domain cannot oversubscribe.

## B. AI monitoring remains scheduler-owned and provider-quota bounded

### Authority rule

Laya or any connected AI provider may analyse only a task explicitly created by AlgoFortis. AI cannot choose or expand its own:

- instrument universe,
- symbols/contracts,
- monitoring frequency,
- next-run time,
- data window,
- trading session,
- concurrency,
- provider/model,
- task TTL,
- or execution scope.

The owner-configured AlgoFortis monitoring policy and deterministic scheduler remain the sole monitoring-schedule/scope authority. `PrimeOrchestrator` may route an already-authorized AI job to an enabled provider/model, but routing does not grant scheduling, RiskGate, capital-allocation, or broker authority.

### Provider rate-limit/quota queue

Each provider gets a bounded deterministic queue governed by versioned provider policy/evidence, not hardcoded guessed production limits. Policy may supply provider-specific concurrency/rate/quota/queue limits and retry timing.

When provider capacity is unavailable because the provider quota or rate limit is exhausted:

- the AI check remains queued only while its task TTL is valid,
- no extra provider call may bypass the queue,
- queue order is deterministic,
- expired/stale checks are never executed later as if fresh,
- provider failure or quota exhaustion cannot promote AI authority or open a broker path,
- there is no silent cross-provider fallback unless a separately qualified owner policy explicitly permits one.

### Queue priority

AI checks use the same deterministic seven-stage candidate-priority policy where the fields are already available from non-AI evidence before the AI call:

1. deterministic hard/pre-eligibility,
2. current portfolio/exposure interaction,
3. strategy priority,
4. pre-AI deterministic edge/quality metric,
5. precomputed capital-efficiency evidence,
6. signal/event timestamp,
7. stable candidate/job identity.

An AI-generated score or conclusion must never determine that same job's place in the provider queue. If a priority field is unavailable before dispatch, the scheduler uses the plan's deterministic neutral/default ordering rule; it must not ask AI to invent the missing priority.

### Required tests

Qualification/regression coverage must prove:

- AI cannot self-schedule a new check.
- AI cannot add a symbol/instrument outside the assigned task scope.
- AI cannot modify its frequency or task TTL.
- provider quota exhaustion queues jobs instead of spawning parallel bypass calls.
- the same input jobs produce the same queue order.
- an expired queued job is dropped/blocked as stale and is not executed.
- no AI output can directly mint `ApprovedOrder`, reserve account capital, arm Live, or call broker mutation.
- different providers may process their own bounded queues independently only when routing policy explicitly assigns them; this does not imply automatic fallback.

## Integration into the existing nine-task plan

- **Task 2/3:** harden capacity identity to `(broker_id, broker_account_ref)` and add deterministic same-account candidate arbitration before reservation/execution.
- **Task 8:** add E2E cases for same-account simultaneous candidates, different-account independent processing, correlated exposure, pending-order reservation retention, and deterministic tie-breaks.
- **AI plane before any AI-assisted trading integration:** add deterministic monitoring scheduler/provider queue coverage above. Current AI remains `RESEARCH`/`SHADOW` and advisory-only until separately qualified for any broader product role.
- **Task 9:** final evidence must state that account domains are isolated and AI provider queue/scope authority tests executed; absence of executable evidence remains NOT GREEN.

These rules strengthen existing safety boundaries; they do not open real-money mutation and do not alter `RiskGateV2` as the sole executable-order approval authority.
