# AlgoFortis V2 — G6 Read-Only Session Evidence Template

**Purpose:** Redacted observation-only qualification record.  
**Standing state:** `READ_ONLY / DISARMED`  
**Mutation authorization:** NONE

> Never paste or commit API keys, access/refresh tokens, passwords, TOTP material, account/UCC identifiers, PAN, phone/email, IP ownership secrets, or raw broker payloads containing personal data.

## Session header

- Evidence date/time (timezone-aware):
- Exact git head SHA:
- Broker profile reference/version:
- Rule-review reference/version:
- Rate-policy reference/version:
- Order-policy reference/version:
- Protection-capability evidence reference/version:
- S2 qualification reference:
- Qualification-policy reference defining required session count:
- Session ordinal under that frozen policy:

## Read-only boundary proof

- `check_phase6_live_readonly.py` result:
- `assert_read_only_broker_conformance(...)` result:
- Callable mutation methods discovered: expected `NONE`
- Legacy Angel adapter loaded: expected `NO`
- `ApprovedOrder` reachable from Phase-6 boundary: expected `NO`
- `LIVE_STATE`: expected `READ_ONLY / DISARMED`

## Redacted session health

Record references/states only; do not record token values.

- Session state:
- Observation available:
- Daily-boundary state:
- Auth/refresh failure observed (if applicable):
- Error text redaction verified:
- Reconnect auto-arm observed: expected `NO`

## Broker-truth observations

Record counts/classifications only unless an approved redaction policy allows more.

- Orders observation status:
- Open-order count:
- Positions observation status:
- Position count:
- Funds observation status:
- Broker truth complete enough for reconciliation: `YES / NO`
- Any partial/malformed response: `YES / NO`
- Any query uncertainty converted to clean-empty state: expected `NO`

## Reconciliation verdict

Authority must remain `engine/reconciliation/live_reconciler.py`.

- Reconciliation report clean: `YES / NO`
- Foreign broker orders detected:
- Foreign broker positions detected:
- Other discrepancy classes:
- Broker-truth errors:
- New-entry eligibility granted by Phase 6: expected `NO`

## Shared incident / alert evidence

Use existing Phase-5 `FailureIncident` / alert pipeline.

- Incident IDs (non-personal deterministic refs only):
- Incident types:
- Severity:
- Halt latched:
- Alert delivery refs:
- Duplicate unresolved observation generated duplicate alert: expected `NO`
- Any secret/raw broker exception text leaked into alert: expected `NO`

## Connectivity / expiry / rate-limit evidence

- Disconnect case exercised:
- Reconnect case exercised:
- Expiry case exercised:
- Refresh-failure case exercised:
- Rate-limit case exercised:
- Any case auto-armed Live: expected `NO`
- Any unbounded retry: expected `NO`

## Broker protection capability evidence

- Required protection policy reference:
- Verified supported capabilities:
- Missing/unknown capabilities:
- Existing broker protection observed:
- Ownership independently verified:
- Auto-adoption performed: expected `NO` unless separately qualified ownership evidence explicitly permits classification only
- `disarmed_required`: expected `TRUE` throughout G6

## Deterministic G6 evidence

- Probe fingerprint Windows A:
- Probe fingerprint Windows B:
- Byte-identical compare result:
- Artifact IDs:
- Workflow/run IDs:

Required markers:

- `BROKER_BOUNDARY=V2_ISOLATED_READ_ONLY`
- `RECONCILIATION_AUTHORITY=LIVE_RECONCILER`
- `FOREIGN_ACTIVITY_INCIDENT_MODEL=PHASE5_SHARED`
- `LIVE_STATE=READ_ONLY/DISARMED`
- `REAL_BROKER_MUTATION_CAPABILITY=ABSENT`
- `G6_ENABLES_REAL_MONEY_TRADING=NO`

## Full regression preservation

- Full regression result:
- Golden result:
- G4 preservation result:
- G5 preservation result:
- GP-S2 preservation result:

## Limitations / unresolved items

- 

## Qualification decision

- `G6 status`: `NOT QUALIFIED / QUALIFIED`
- Reviewer/date:
- Reason:

A `QUALIFIED` G6 decision still **does not enable real-money trading**. Live remains `READ_ONLY / DISARMED` until a later separately authorized release gate.
