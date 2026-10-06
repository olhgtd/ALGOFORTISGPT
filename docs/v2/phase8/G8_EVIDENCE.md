# AlgoFortis V2 — G8 AI / Agents Intelligence Evidence (legacy qualification record)

**Date:** 2026-09-27  
**Status:** **NOT QUALIFIED — HOSTED EXECUTION EVIDENCE UNAVAILABLE**  
**Mode:** Independent intelligence candidates  
**Live:** `READ_ONLY / DISARMED`

## 1. Dependency and implementation heads

- Phase-5 dependency/base head used to start Phase 8: `8b2f9849c5cd064d0169ac40601dae6fb62b87fe` (`v2-phase5-paper-recovery`).
- Phase-8 qualification-code head: `b04eff07f8c5968f48b5671fbe6b1d4cbcdae005`.
- Final reviewed code/config head after removal of the temporary development workflow: `fd4f0f8d84adbe9166095af6e0759ba9cf2c937d`.
- Canonical implementation PR: #18, `v2-phase8-ai-shadow-impl` -> `v2-phase5-paper-recovery`, draft/unmerged.
- This evidence-file update is documentation-only and does not change the qualified runtime/workflow tree recorded above.

## 2. Implemented G8 safety scope

Phase 8 implements the approved V2.0 Research + Shadow boundary:

- one local + one cloud provider seam behind the common provider/registry authority;
- provider data classification, allowlist/redaction and Data V2 licensing/provenance egress gate;
- non-executable immutable `TradeCandidate` with deterministic TTL validation;
- stale/expired candidate -> `NO_TRADE` / `HOLD`;
- deny-by-default Tool Gateway with declared scope/budget/quota/audit;
- Prime/Research/Risk-Challenger research orchestration only;
- untrusted-content / prompt-injection boundary;
- bounded market-intelligence scheduler with no broker/order job vocabulary;
- per-user policy-bound memory with forbidden secret/account/trade-log classes;
- independent candidate evidence is routed into the common deterministic candidate/risk lifecycle;
- safe AI audit/replay and fail-closed provider fallback;
- deterministic G8 evidence/probe + dual-Windows qualification workflow.

Committee/ensemble scope remains deferred T2. No Phase-8 component is authorized to mint `ApprovedOrder`, arm Live, submit broker orders, widen risk, change kill switches, or auto-promote a strategy/model.

## 3. Local focused evidence observed during implementation

The following RED -> GREEN focused runs were observed in isolated local sandboxes for the later implementation slices:

- Task 9 prompt-injection + market-intelligence scheduler: **9/9 PASS**.
- Phase-8 firewall `urllib.parse` false-positive regression: **4/4 PASS** after RED reproduction; `urllib.request` remains forbidden.
- Task 10 memory boundary: **11/11 PASS**.
- Task 11 shadow mode: **5/5 PASS**.
- Task 12 audit/replay + provider outage/fallback: **7/7 PASS**.
- Task 13 deterministic evidence + qualification guard: **5/5 PASS**.
- Task-13 deterministic probe fingerprint: `c630dba24720759841818f5ddc5d88fd40025c3b913490847c94c9ba852fb353`.

These focused local results are development evidence only. They are **not** a substitute for the required exact-head hosted Windows qualification or a branch-wide full regression run.

## 4. Required deterministic markers

The G8 probe binds the following markers:

- `AI_AUTHORITY=INDEPENDENT_CANDIDATE_SOURCE`
- `APPROVED_ORDER_AUTHORITY=RISK_GATE_V2_ONLY`
- `PROVIDER_SCOPE=ONE_LOCAL_ONE_CLOUD`
- `COMMITTEE_ENSEMBLE=DEFERRED_T2`
- `PROVIDER_DATA_GATE=ALLOWLIST_REDACT_FAIL_CLOSED`
- `CLOUD_DATA_EGRESS=LICENSING_PROVENANCE_REQUIRED`
- `TRADE_CANDIDATE=NON_EXECUTABLE_TTL_PROVENANCE`
- `STALE_CANDIDATE=DISCARD_NO_TRADE`
- `TOOL_GATEWAY=DENY_BY_DEFAULT_QUOTA_AUDIT`
- `PROMPT_INJECTION=UNTRUSTED_CONTENT_BOUNDARY`
- `PROVIDER_OUTAGE=NO_TRADE_OR_APPROVED_FALLBACK`
- `LIVE_STATE=READ_ONLY/DISARMED`
- `G8_ENABLES_REAL_MONEY_TRADING=NO`

## 5. Hosted runner evidence / blocker

GitHub hosted execution remains externally blocked before repository steps start.

Final code/config head qualification attempt:

- workflow: `V2 Phase 8 AI Shadow Qualification`
- run ID: `36297188757`
- head: `fd4f0f8d84adbe9166095af6e0759ba9cf2c937d`
- `g8-windows-latest` job ID `108558114043`: `failure`, **`steps=null`**
- `g8-windows-2022` job ID `108558113966`: `failure`, **`steps=null`**
- `G8 cross-Windows compare` job ID `108558122761`: `skipped`, **`steps=null`**

No checkout, Python setup, dependency install, static firewall, pytest, deterministic probe, artifact upload, or cross-Windows compare step executed. The failure therefore occurred before repository code/test execution.

The same pre-step provisioning pattern has already affected Phase 5/6/7 verification attempts. This result is recorded as **runner/infrastructure execution unavailable**, not as a repository code-test failure and not as GREEN evidence.

The final G8 workflow requires:

1. Windows latest / Python 3.13.14 focused + dependency regression pass;
2. Windows 2022 / Python 3.13.14 focused + dependency regression pass;
3. Phase-8 static firewall pass on both legs;
4. deterministic G8 probe artifacts on both legs;
5. cross-Windows normalized evidence comparison PASS.

Until those steps actually execute successfully, G8 remains **NOT QUALIFIED**.

## 6. Safety conclusion

**G8 GREEN, even when eventually obtained, does not enable real-money trading.**

Current and required standing state remains:

- Live = `READ_ONLY / DISARMED`;
- AI/Laya = independent candidate/intelligence source;
- no direct AI -> broker/order path;
- no AI `ApprovedOrder` mint authority;
- no cloud egress without positive licensing/provenance + policy/redaction evidence;
- provider/tool/audit failure remains fail-closed;
- stale candidates remain discarded as `NO_TRADE` / `HOLD`.
