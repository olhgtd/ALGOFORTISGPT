# Manual V1 Exclusions, Deferred Work & Non-Migration Rules

## Known final-V1 deferred/nonblocking items

The final manual certification explicitly carried/deferred items including:

- dedicated GUI recovery-management screen;
- real broker place/modify/cancel execution;
- true fresh-PC hardware validation outside the development machine;
- non-Upstox native WebSocket streaming feeds;
- Dhan credential-binding limitation requiring external broker/OAuth/static-IP/webhook behavior;
- a small 360px fail-closed overlay clipping issue;
- external protective resolvers deferred beyond V1.

These do not erase the value of the V1 baseline, but they must not be misreported as already solved by the manual package.

## Product/UI truthfulness caveats

Historical final certification noted some intentionally non-live/preview surfaces, including:

- Owner user-inspection tabs containing sample summary projections;
- reports export showing a simulated-preview notice;
- some dev-gated/display-only surfaces.

When salvaging UI, preserve layout/workflow value but **do not restore sample/fake-success data as authoritative product state**.

Missing authority must render truthfully as `UNKNOWN`, `UNAVAILABLE`, `STALE`, disabled, or equivalent current contract state.

## Do not migrate these runtime authorities

### Old Risk/order authority

Do not create a second executable-order approval path from V1. Current `RiskGateV2` remains the sole executable-order authority.

### Old Paper authority

Do not run a duplicate V1 Paper engine next to V2 Paper. Salvage tests, UX and fill/recovery knowledge only.

### Old broker mutation paths

Do not re-enable any V1 place/modify/cancel implementation. Live remains READ_ONLY/DISARMED until a separately-qualified current release explicitly changes that.

### Old local-only account authority

LOCAL_PRIVATE auth is valuable implementation reference but is not a replacement for current account/device/session architecture.

### Old database files

Never copy an old V1 SQLite/security/governance/live-state file into current runtime as authority.

Allowed uses:

- migration fixture;
- schema reference;
- compatibility test;
- disaster-recovery fixture after sanitization.

## Generated/duplicate/junk content — IGNORE

Never migrate these merely because they exist in the Drive archive:

- `.kilo/worktrees/ember-health` (duplicate repository/worktree tree identified during earlier audit);
- any other `.kilo/worktrees/*` copies unless explicitly needed as forensic evidence;
- `node_modules/`;
- `dist/` output as source authority;
- staged build directories;
- `__pycache__/`;
- `.pytest_cache/`;
- IDE/editor caches;
- downloaded dependency caches;
- old installer `.exe` artifacts as source code;
- screenshots/evidence duplicates;
- temporary audit scratch files;
- generated test output;
- repeated packaged copies of source already represented canonically elsewhere.

## Legacy naming

Do not mass-delete every `SentinelX` string blindly.

Rules:

- visible current product identity = **AlgoFortis**;
- legacy internal schema/database/environment identifiers may remain when compatibility requires them;
- rename only when a reviewed compatibility/migration path exists.

## Raw Drive archive is evidence, not a merge target

Never do:

```text
unzip AlgoFortis_FINAL.zip
copy everything into current branch
commit
```

Correct process:

```text
identify capability
  ↓
check ADOPTION_MATRIX
  ↓
locate V1 test/source
  ↓
compare with current V2 contract
  ↓
port regression test
  ↓
adapt minimal implementation
  ↓
current qualification
```

## Things V1 completion did not prove

Do not infer from `V1 STATUS = COMPLETE` that V1 had production-complete:

- AWS central account authority;
- remote hosted engine;
- mobile app;
- public self-signup;
- real-money Live execution;
- broker-secret cloud storage (explicitly forbidden);
- cloud order execution (explicitly forbidden);
- complete public update/signing channel;
- full commercial entitlement/billing platform;
- all-broker native WebSocket streaming.

## Permanent safety carry-forward

The V1 source may contribute behavior and tests, but it cannot weaken these current rules:

- uncertainty fails closed;
- Paper cannot reach real broker mutation;
- restart/reconnect does not auto-arm;
- recovery/reconciliation precede retry/new entries;
- AI/Laya cannot bypass deterministic validation/RiskGate/execution authority;
- broker secrets remain local;
- cloud/account authority is not trading authority;
- Live remains READ_ONLY/DISARMED until explicitly qualified otherwise.
