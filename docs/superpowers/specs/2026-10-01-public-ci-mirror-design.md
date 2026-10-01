# AlgoFortis Public CI Mirror Design

**Date:** 2026-10-01  
**Status:** APPROVED DESIGN — implementation not started  
**Private source repo:** `olhgtd/ALGOFORTISGPT`  
**Public CI repo:** `olhgtd/AlgoFortis-Local-V1-RC1`

## 1. Goal

Create a disposable, sanitized public CI mirror that can run GitHub-hosted Actions without exposing the full private AlgoFortis repository, its historical Git graph, unrelated product code, local state, credentials, or proprietary runtime data. The first target is Phase 8 exact-head qualification; the mechanism must be reusable for later phases.

## 2. Source of Truth

`olhgtd/ALGOFORTISGPT` remains the only authoritative product repository. The public CI mirror is never a product source of truth and must never be used as the canonical development history.

The first source snapshot is Phase 8 exact head:

`3cfaba5d3768d116ff3999dd76e73c0a742943d1`

Phase 8 safety invariants remain unchanged:

- AI authority: `RESEARCH_SHADOW_ONLY`.
- `RiskGateV2` remains the sole ApprovedOrder authority.
- Live remains `READ_ONLY/DISARMED`.
- The CI mirror must not enable broker mutation, Live arming, credential access, or real-money execution.

## 3. Mirror Model

The public repo contains a fresh snapshot only, not a clone of the private repo's Git history.

Each qualification snapshot has one manifest recording:

- private source repository name;
- exact private source commit SHA;
- phase/gate identifier;
- included file paths;
- excluded classes of files;
- mirror snapshot version;
- generated-at timestamp;
- expected qualification workflows.

No private parent commit IDs are required beyond the single exact source SHA needed for traceability.

## 4. Inclusion Policy

Include only files required to execute the target gate and its explicitly required dependency regressions:

- target phase implementation modules;
- direct Python package dependencies needed by those modules/tests;
- target phase tests;
- explicitly required dependency-regression tests;
- static architecture/safety guards;
- deterministic evidence probes;
- required lock/input dependency files;
- GitHub Actions workflows adapted only where necessary to run in the mirror;
- minimal package initializers and non-secret configuration required for import/test discovery.

The mirror must prefer minimum required files over broad directory copying.

## 5. Mandatory Exclusions

The mirror must not contain:

- `.git` history from the private source repo;
- `.env` or `.env.*`;
- API keys, access tokens, refresh tokens, PATs, passwords, recovery codes, private keys, certificates, or broker credentials;
- local databases, SQLite files, WAL/SHM files, runtime state, local AppData, session state, device keys, or activation secrets;
- real user data, account identifiers, balances, positions, unrestricted trade logs, support data, or screenshots containing private data;
- bulk market datasets or local imported data;
- unrelated strategies or product modules not needed by the qualification gate;
- generated binaries/installers;
- unrelated historical branches or PR history.

## 6. Secret and Privacy Gate

Before any snapshot is published, the candidate file set must pass a fail-closed pre-publication scan covering at least:

- common credential/key prefixes and assignment patterns;
- PEM/private-key headers;
- GitHub/OpenAI/AWS-style token signatures;
- bearer tokens and authorization headers with literal values;
- suspicious `.env`/secret/credential file names;
- local DB/runtime-state file extensions;
- high-risk files outside the allowlisted mirror manifest.

Hits that are clearly test fixtures, variable names, redaction rules, or deny-list strings may be allowlisted only by exact path + exact reason. Unknown or ambiguous findings block publication.

## 7. Phase 8 Qualification Scope

The first mirror must reproduce the current Phase 8 gate semantics, including:

- Phase 8 static firewall;
- all `tests_v1/test_phase8_*.py` tests present at exact source head;
- required Phase 1 adapter-registry dependency regression;
- required Phase 3 data-licensing dependency regression;
- deterministic G8 evidence generation on `windows-latest`;
- deterministic G8 evidence generation on `windows-2022`;
- cross-Windows evidence comparison on Ubuntu;
- required safety marker checks.

Where broader Phase 5/6/7/reunion regressions are needed before private merge, those should be mirrored as explicit additional workflows/snapshots rather than silently widening the Phase 8 file set.

## 8. CI Workflow Rules

Public mirror workflows must:

- use read-only repository permissions unless a stronger permission is strictly required;
- never use private-repo secrets;
- never require broker/API credentials;
- install dependencies from checked-in lock/input files only;
- upload only deterministic qualification artifacts that contain no private data;
- fail closed on missing tests, missing guard files, missing evidence, or evidence mismatch;
- never mark the private source PR qualified unless the mirror manifest source SHA exactly equals the private PR head SHA being assessed.

## 9. Evidence and Promotion Back to Private Repo

A mirror run may support private qualification only when all of the following are true:

1. Manifest exact source SHA matches the private PR head.
2. Required workflows actually execute; zero-step/runner-allocation failures do not count as software evidence.
3. All required jobs pass.
4. Deterministic artifacts compare exactly where required.
5. Safety markers remain unchanged.
6. Any code fixes made during public CI are recreated or cherry-picked into the private source repo and the exact-source SHA is refreshed before claiming final qualification.

The public mirror never merges directly into private `main`. Product changes are reviewed and integrated through the private repository's normal PR path.

## 10. Reuse for Later Phases

The same public repo may be reused by replacing its working snapshot with a new clean snapshot. Every new phase must get a new manifest version and exact private source SHA. Files left over from a previous phase that are not required by the new manifest must be removed.

Phase 9 must remain subject to its separate software and legal/compliance gates; public CI cannot convert external legal review into software evidence.

## 11. Failure Handling

- Secret/privacy scan failure -> do not publish/update the public snapshot.
- Missing dependency discovered during CI -> add only the minimum required dependency file/module, update manifest, rescan, rerun.
- Test/guard failure -> fix in private source first or reproduce the minimal fix in the mirror, then reconcile back to private source and refresh source SHA.
- Public mirror drift from private exact head -> qualification invalid until refreshed.
- Runner provisioning failure with zero executed steps -> infrastructure failure, not code failure.

## 12. Success Criteria

The design is successful when:

- the private AlgoFortis repo remains private;
- the public repo contains only a sanitized, manifest-defined snapshot;
- Phase 8 required jobs execute on public GitHub-hosted runners;
- deterministic Windows evidence matches;
- no secret/private-state material is exposed;
- the exact qualified source SHA is traceable back to the private PR;
- Live remains `READ_ONLY/DISARMED` and AI remains `RESEARCH_SHADOW_ONLY`;
- the mirror process can be repeated for Phase 9 and later gates without copying full private history.
