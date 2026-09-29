# Slice 1 — V1 Security & Platform Salvage

## Purpose

Carry forward the highest-value verified manual-V1 security/platform behaviors into the current AlgoFortis convergence tree without importing old runtime authorities.

## Branch

`v1-salvage-integration-20260929`

## Intended base

`v2-convergence-v1-salvage-20260928` at `7a51807b4dd5a0788ec3bf32a228f771867ddb2f`.

The implementation branch also contains the Slice-1 plan commit. The source convergence branch remains the authoritative pre-salvage baseline.

## Manual V1 reference

Reference branch: `v1-manual-salvage-reference-20260929`

Primary reference files:

- `V1_SALVAGE_REFERENCE_README.md`
- `docs/v1-salvage-reference/ADOPTION_MATRIX.md`
- `docs/v1-salvage-reference/PATH_AND_CAPABILITY_MAP.md`
- `docs/v1-salvage-reference/SECURITY_RECHECK.md`
- `docs/v1-salvage-reference/CERTIFIED_SCOPE.md`

## Included in Slice 1

1. Security regression invariants
   - no plaintext secrets;
   - fail-closed authorization;
   - session/token-reuse behavior where current authority exposes it;
   - recovery cannot grant trading authority.

2. Backup/restore security invariants
   - secret/private-key exclusion;
   - path-traversal/duplicate-member rejection;
   - checksum/manifest fail-closed behavior.

3. Recovery/idempotency compatibility
   - duplicate suppression;
   - corrupt-state fail-closed;
   - restart/reconnect never auto-arms;
   - current RECOVERY/READY_FOR_RESUME/manual-resume semantics win.

4. Static authority boundaries
   - no second RiskGate;
   - no second Paper execution authority;
   - no broker mutation enablement;
   - no legacy local identity authority replacing current account contracts.

## Explicitly excluded from Slice 1

- dashboard visual migration;
- Owner/User screen migration;
- broker feature expansion;
- real broker place/modify/cancel;
- Laya integration/training;
- old V1 database import;
- old installer binaries;
- `.kilo/worktrees`, caches, build output, `node_modules`;
- SAMPLE/demo/fake-success state.

## Permanent safety invariants

```ini
READ_ONLY=true
DISARMED=true
live_global_hold=true
real broker mutation=DISABLED
```

`RiskGateV2` remains the sole executable-order authority.

## Salvage method

For each capability:

1. locate current V2 behavior;
2. port or write the V1-derived regression test first;
3. observe RED if the behavior is missing, or record that current V2 already satisfies it;
4. implement only the minimum compatible change if needed;
5. verify targeted + wider regression;
6. never transplant an old authority wholesale.
