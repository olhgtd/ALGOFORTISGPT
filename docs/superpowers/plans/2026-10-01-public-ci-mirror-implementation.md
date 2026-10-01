# AlgoFortis Public CI Mirror Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable sanitized public CI mirror that qualifies the exact Phase 8 private source head on free GitHub-hosted Windows runners without exposing the full private repository or changing AlgoFortis trading authority.

**Architecture:** `olhgtd/ALGOFORTISGPT` remains the authoritative private product repository. `olhgtd/AlgoFortis-Local-V1-RC1` is a disposable public snapshot containing only a manifest-defined dependency closure for the target gate, plus read-only CI workflows and deterministic evidence. Any code fix is reconciled back into the private PR; the public mirror never becomes product source-of-truth.

**Tech Stack:** GitHub Actions, Python 3.13.14, pytest, PowerShell, stdlib JSON/hashlib/pathlib, existing AlgoFortis Phase 8 safety guards and deterministic probes.

**Spec:** `docs/superpowers/specs/2026-10-01-public-ci-mirror-design.md`

## Global Constraints

- Private source repo remains `olhgtd/ALGOFORTISGPT`.
- Public mirror repo is `olhgtd/AlgoFortis-Local-V1-RC1`.
- First exact source SHA is `3cfaba5d3768d116ff3999dd76e73c0a742943d1`.
- AI authority remains `RESEARCH_SHADOW_ONLY`.
- `RiskGateV2` remains the sole ApprovedOrder authority.
- Live remains `READ_ONLY/DISARMED`.
- No broker/API credentials, `.env`, private keys, local DB/runtime state, real user/account data, bulk market data, unrestricted trade logs, or private Git history enter the public mirror.
- Public workflows use `permissions: contents: read` and no private-repo secrets.
- Zero-step runner failures are infrastructure failures, never software qualification evidence.
- A public result can qualify a private PR only when the manifest source SHA exactly equals the private PR head under assessment.

## Review Focus

1. **Manifest drift:** a private PR head changes after snapshot creation; mirror must fail qualification until source SHA and content are refreshed.
2. **Secret-like fixture false positives:** deny-list strings and test canaries may exist; only exact-path/exact-reason allowlists are acceptable, while ambiguous findings block publication.
3. **Missing dependency closure:** a Phase 8 import needs a non-Phase-8 module; add only the minimum exact dependency file/package, update the manifest, rescan, and rerun.
4. **Workflow weakening:** adapted public workflow must preserve Windows latest + Windows 2022 + deterministic compare and safety markers; no gate may be silently removed to make CI green.
5. **Public/private code divergence after a fix:** if mirror code changes, recreate/reconcile it in private PR, refresh source SHA, regenerate the snapshot, and requalify before merge.

---

### Task 1: Freeze the Phase 8 Mirror Manifest and Publication Policy

**Files:**
- Create in public mirror: `CI_MIRROR_MANIFEST.json`
- Create in public mirror: `README.md`
- Reference private source: PR #25 head `3cfaba5d3768d116ff3999dd76e73c0a742943d1`

**Interfaces:**
- Consumes: exact private source head and Phase 8 PR changed-file inventory.
- Produces: machine-readable manifest with `source_repo`, `source_sha`, `gate`, `snapshot_version`, `included_paths`, `excluded_classes`, `expected_workflows`, and `safety_markers`.

- [ ] **Step 1: Define the initial Phase 8 inclusion set**

Include the exact Phase 8 runtime and gate files:
- `engine/ai/v2/**`
- `engine/data/licensing.py`
- `engine/core/adapter_registry.py`
- `engine/reproducibility/codec.py`
- `build/tools/check_phase8_ai_shadow.py`
- `build/tools/phase8_ai_probe.py`
- all `tests_v1/test_phase8_*.py`
- `tests_v1/test_v2_phase1_adapter_registry.py`
- `tests_v1/test_v2_phase3_data_licensing.py`
- `requirements-runtime.lock.txt`
- `requirements-dashboard.in`
- `requirements-test.in`
- `.github/workflows/v2-phase8-ai-shadow.yml`

Do not include Phase 7, broker adapters, Live modules, strategy directories, user data, databases, local state, or unrelated dashboard/product files unless CI proves an import dependency is genuinely required.

- [ ] **Step 2: Write `CI_MIRROR_MANIFEST.json`**

Required values:
- `source_repo`: `olhgtd/ALGOFORTISGPT`
- `source_sha`: `3cfaba5d3768d116ff3999dd76e73c0a742943d1`
- `gate`: `G8`
- `phase`: `8`
- `ai_authority`: `RESEARCH_SHADOW_ONLY`
- `live_state`: `READ_ONLY/DISARMED`
- `real_money_trading_enabled`: `false`
- explicit included paths and excluded classes.

- [ ] **Step 3: Write public `README.md`**

State that this repository is a disposable CI snapshot, not the product source-of-truth; no credentials or real account/trading data belong here; exact source SHA is recorded in the manifest.

- [ ] **Step 4: Verify manifest/source alignment before copying code**

Check private PR #25 metadata and require its head to equal the manifest source SHA.

Expected: exact equality with `3cfaba5d3768d116ff3999dd76e73c0a742943d1`.

- [ ] **Step 5: Commit the public manifest/README as the first snapshot commit**

Expected: public repo has one clean snapshot lineage and no copied private Git history.

---

### Task 2: Pre-Publication Secret/Privacy Gate and Minimal File Copy

**Files:**
- Populate paths listed by `CI_MIRROR_MANIFEST.json` in `olhgtd/AlgoFortis-Local-V1-RC1`.
- Do not create `.env`, credential, DB, data-dump, log, session, key, or local-state files.

**Interfaces:**
- Consumes: manifest allowlist and exact private source SHA.
- Produces: sanitized public working tree with preserved relative import paths.

- [ ] **Step 1: Fetch every candidate file from the exact private source ref**

Use the exact source commit/ref, never moving `main` implicitly.

- [ ] **Step 2: Scan each candidate before public write**

Block publication on ambiguous matches for:
- PEM/private-key headers;
- GitHub/OpenAI/AWS-style live-token signatures;
- literal bearer/authorization secrets;
- password/API-secret/token assignments with non-fixture values;
- forbidden file names/extensions (`.env*`, `*.pem`, `*.key`, `*.pfx`, `*.p12`, `*.db`, `*.sqlite*`, `*.wal`, `*.shm`, credential/token/session files).

Known code strings such as `api_key`, `BROKER_CREDENTIAL`, `PRIVATE_KEY`, deny-list markers, and explicit test canaries are allowed only when the exact file and reason are reviewed.

- [ ] **Step 3: Copy the initial manifest set preserving paths**

Copy content byte-for-text-equivalent where no workflow adaptation is necessary. Preserve package paths so imports stay identical to private qualification semantics.

- [ ] **Step 4: Verify public tree contains no unmanifested source paths**

Expected: every public product/test/workflow file is represented by the manifest or is one of `README.md` / `CI_MIRROR_MANIFEST.json`.

- [ ] **Step 5: Commit the sanitized source snapshot**

Commit message: `ci: stage sanitized G8 source snapshot`.

---

### Task 3: Adapt and Lock the Public G8 Workflow Without Weakening It

**Files:**
- Modify public mirror only: `.github/workflows/v2-phase8-ai-shadow.yml`
- Test behavior through existing `tests_v1/test_phase8_ai_qualification_guard.py`

**Interfaces:**
- Consumes: existing private Phase 8 workflow semantics.
- Produces: public workflow with the same dual-Windows qualification and deterministic compare, triggerable in the public mirror.

- [ ] **Step 1: Preserve required jobs and Python version**

Required jobs:
- `windows-latest` on Python `3.13.14`;
- `windows-2022` on Python `3.13.14`;
- Ubuntu deterministic artifact compare.

- [ ] **Step 2: Preserve dependency install and fail-closed test discovery**

Both Windows legs must install checked-in requirement files, run `python build/tools/check_phase8_ai_shadow.py`, discover `tests_v1/test_phase8_*.py`, fail if none exist, then run Phase 8 tests plus the Phase 1 adapter-registry and Phase 3 licensing regressions.

- [ ] **Step 3: Preserve deterministic probe artifacts**

Both Windows legs run `python build/tools/phase8_ai_probe.py`; upload separate artifacts; compare normalized text exactly on Ubuntu.

- [ ] **Step 4: Add explicit safety-marker assertions to the compare job**

Require at minimum:
- `AI_AUTHORITY=RESEARCH_SHADOW_ONLY`
- `APPROVED_ORDER_AUTHORITY=RISK_GATE_V2_ONLY`
- `LIVE_STATE=READ_ONLY/DISARMED`
- `G8_ENABLES_REAL_MONEY_TRADING=NO`

- [ ] **Step 5: Keep workflow permissions read-only and remove any unused private branch trigger**

`permissions: contents: read`; support `push` to `main` and/or `workflow_dispatch` in the mirror. Do not add secrets or write permissions.

- [ ] **Step 6: Commit workflow adaptation**

Commit message: `ci: lock public G8 dual-Windows qualification`.

---

### Task 4: Execute G8, Close Only Genuine Dependency Gaps, and Capture Evidence

**Files:**
- Public workflow run and artifacts.
- Manifest updates only if an exact missing dependency is discovered.

**Interfaces:**
- Consumes: public sanitized snapshot.
- Produces: executed G8 Windows evidence and cross-Windows comparison.

- [ ] **Step 1: Trigger the public G8 workflow**

Expected: jobs obtain real runners and contain checkout/setup/install/test/probe steps. `steps=[]` is not accepted as test evidence.

- [ ] **Step 2: If import collection fails, identify the first missing private dependency**

Add only the exact required module/package file(s), update `included_paths`, repeat the pre-publication scan, and rerun. Do not respond to an import failure by copying broad directories.

- [ ] **Step 3: If a test or static guard fails, classify it**

- Mirror packaging/adaptation bug -> fix mirror setup only.
- Genuine Phase 8 code bug -> fix/reconcile in private PR first, then refresh source SHA and regenerate affected mirror files.
- Runner zero-step failure -> treat as infrastructure failure and retry; do not edit code to address it.

- [ ] **Step 4: Require both Windows jobs GREEN**

Expected: Phase 8 static firewall PASS; focused tests + dependency regressions PASS; each probe artifact produced.

- [ ] **Step 5: Require cross-Windows compare GREEN**

Expected: normalized evidence text exact-match and all safety-marker assertions PASS.

- [ ] **Step 6: Record run IDs, job IDs, artifact names, exact manifest source SHA, and conclusions**

This evidence is the audit trail used to support the private PR review.

---

### Task 5: Private PR Reconciliation and Exact-Head Qualification Decision

**Files:**
- Private PR #25 metadata/evidence docs only as needed.
- Do not merge public mirror directly into private `main`.

**Interfaces:**
- Consumes: successful public G8 evidence and exact source SHA.
- Produces: a merge/no-merge decision for private Phase 8 PR based on exact-head evidence.

- [ ] **Step 1: Re-fetch private PR #25 head**

If head differs from mirror `source_sha`, public qualification is stale and cannot qualify the PR.

- [ ] **Step 2: Reconcile any genuine code fixes into private PR**

After any private code change, update the manifest source SHA and rerun the public qualification from the refreshed snapshot.

- [ ] **Step 3: Verify private safety invariants independently**

PR description/code must still state/implement:
- AI `RESEARCH_SHADOW_ONLY`;
- sole ApprovedOrder authority remains `RiskGateV2`;
- Live `READ_ONLY/DISARMED`;
- no real-money authorization.

- [ ] **Step 4: Attach qualification evidence to the private review trail**

Record public run/job/artifact identifiers and exact mirror source SHA. Never describe an unexecuted or zero-step run as GREEN.

- [ ] **Step 5: Merge Phase 8 only if all exact-head blockers are cleared**

Use expected-head protection when merging. If required broader Phase 5/6/7/reunion gates remain mandated by the private release plan, run them as separate explicit sanitized public snapshots/workflows before merge rather than silently treating G8 as a substitute.

---

### Task 6: Prepare the Mirror for Phase 9 Reuse

**Files:**
- Replace/update `CI_MIRROR_MANIFEST.json` only after Phase 8 is closed.
- Remove files not required by the next manifest before publishing the next snapshot.

**Interfaces:**
- Consumes: completed Phase 8 mirror process.
- Produces: clean reusable public CI repo for Phase 9 without stale Phase 8 leakage.

- [ ] **Step 1: Freeze Phase 8 evidence before changing the snapshot**

Keep run identifiers and source SHA in the private audit trail.

- [ ] **Step 2: Build a fresh Phase 9 manifest from the Phase 9 exact private head**

Do not reuse Phase 8 source SHA or assume dependency closure is identical.

- [ ] **Step 3: Delete unneeded Phase 8 files from the public working snapshot**

Expected: public tree matches the new manifest, not the union of all historical phases.

- [ ] **Step 4: Keep Phase 9 legal/compliance evidence separate**

Public software CI may prove G9 software behavior but cannot convert `PENDING_EXTERNAL_REVIEW` into completed legal/compliance review.
