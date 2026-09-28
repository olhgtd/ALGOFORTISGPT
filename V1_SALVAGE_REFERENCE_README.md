# AlgoFortis Manual V1 — Salvage Reference Branch

**Branch purpose:** preserve the useful, verified knowledge from the manually-built Google Drive V1 package so AlgoFortis development does not need to repeatedly rediscover, redownload, or reread the large archive.

**Branch:** `v1-manual-salvage-reference-20260929`

**Created from:** `v2-convergence-v1-salvage-20260928` at `7a51807b4dd5a0788ec3bf32a228f771867ddb2f`

## What this branch is

This is an **isolated reference/salvage branch**. It is not a direct V1→V2 merge branch and it must not become a second trading authority.

The manually-built V1 remains a product-feature donor and historical evidence source. Current V2 contracts remain authoritative for trading safety, execution capability, RiskGate, data provenance, recovery semantics, Paper isolation, and AI boundaries.

## What is stored here

Read these files first:

1. `docs/v1-salvage-reference/SOURCE_PROVENANCE.md`
   - exact Drive archive identifiers;
   - final manual V1 certification identity;
   - manifest/fingerprint evidence;
   - archive-access notes.

2. `docs/v1-salvage-reference/CERTIFIED_SCOPE.md`
   - what the final manual V1 was actually certified to do;
   - test/build evidence;
   - what was explicitly outside V1 scope.

3. `docs/v1-salvage-reference/SECURITY_RECHECK.md`
   - security controls worth preserving;
   - controls that must be adapted to V2 rather than copied blindly;
   - fresh revalidation checklist.

4. `docs/v1-salvage-reference/ADOPTION_MATRIX.md`
   - every major V1 capability classified as `ADOPT`, `ADAPT`, `TEST-ONLY`, `REFERENCE`, or `IGNORE`;
   - where each capability belongs in current AlgoFortis.

5. `docs/v1-salvage-reference/PATH_AND_CAPABILITY_MAP.md`
   - important V1 source paths/components already identified from the manual build and audit evidence;
   - intended current-system destination/domain.

6. `docs/v1-salvage-reference/EXCLUSIONS_AND_LIMITATIONS.md`
   - known V1 deferred items;
   - generated/duplicate/junk content that must never be migrated;
   - old authorities that must not be resurrected.

## Permanent salvage rule

> **V2 is the skeleton and authority. V1 is the product-feature donor.**

That means:

- preserve useful V1 UX, platform, security, installer, backup, recovery knowledge and regression cases;
- never create a parallel RiskGate/order/Paper/broker-mutation authority;
- never copy SAMPLE/fake-success behavior into production truth surfaces;
- never treat old SQLite files as current runtime authority;
- migrate behavior through explicit V2 contracts, adapters, read models, migrations and regression tests.

## Raw archive policy

The ~393 MB Drive archive is **not vendored into Git**. The branch stores exact archive pointers and the high-value verified knowledge required for normal development. If an exact old source file is ever needed and is not already represented in current Git history, use `SOURCE_PROVENANCE.md` to retrieve only that source from the canonical Drive package.

This keeps Git clean while avoiding repeated full-audit work.

## Safety baseline carried forward

Until separately qualified and explicitly changed:

```ini
READ_ONLY=true
DISARMED=true
live_global_hold=true
real broker mutation=DISABLED
```

AI/Laya remains research/shadow/candidate-only. RiskGateV2 remains the sole executable-order authority.
