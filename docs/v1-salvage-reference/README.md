# AlgoFortis Manual V1 Salvage Reference

This folder is the durable reference for the manually-built Google Drive V1 package.

## Purpose

Avoid repeatedly downloading and rereading the ~393 MB V1 archive. This branch records the useful, verified product/security/platform knowledge and the exact rules for reusing it in current AlgoFortis.

## Read order

1. `SOURCE_PROVENANCE.md` — canonical Drive package, final manual-V1 identity, manifest evidence.
2. `CERTIFIED_SCOPE.md` — what V1 was actually certified to do and what was outside scope.
3. `SECURITY_RECHECK.md` — security controls worth preserving and controls requiring V2 adaptation.
4. `ADOPTION_MATRIX.md` — KEEP/ADAPT/TEST-ONLY/REFERENCE/IGNORE decisions.
5. `PATH_AND_CAPABILITY_MAP.md` — useful V1 components and where they belong in current AlgoFortis.
6. `EXCLUSIONS_AND_LIMITATIONS.md` — what must not be migrated and known V1 limitations.

## Permanent rule

> V2 is the skeleton and authority. V1 is the product-feature donor.

The branch is a reference/salvage source. It is not a second production line and must never introduce parallel trading authority.

## Current authority rules

- `RiskGateV2` remains the sole executable-order approval authority.
- Paper cannot reach real broker mutation.
- Live remains `READ_ONLY / DISARMED` until separately qualified.
- Recovery/reconciliation precede retry/new entries.
- Old V1 SQLite databases are evidence/migration inputs only, never current runtime authority.
- AI/Laya remains research/shadow/candidate-only.

## What is intentionally NOT copied here

- the raw ~393 MB ZIP;
- `node_modules`;
- build output and installer binaries;
- caches and `__pycache__`;
- screenshots/evidence duplicates;
- `.kilo/worktrees/ember-health` duplicate tree;
- old databases as runtime state;
- any SAMPLE/fake-success presentation.

If an exact old source file is ever needed, use `SOURCE_PROVENANCE.md` and retrieve only that file/source from the canonical Drive package.