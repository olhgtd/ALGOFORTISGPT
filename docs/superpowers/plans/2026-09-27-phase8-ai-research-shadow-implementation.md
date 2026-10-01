# Phase 8 AI / Agents Research + Shadow Implementation Plan

> **Execution rule:** Implement task-by-task with test-driven development. Do not skip RED verification, do not claim G8 GREEN without hosted evidence, and never loosen `READ_ONLY / DISARMED`.

**Goal:** Implement AF2-AIA-001…007 and AF2-AIA-010 as a research/shadow-only AI subsystem with one local and one cloud provider seam, deterministic non-executable `TradeCandidate` validation, deny-by-default tools, prompt-injection defenses, bounded memory/shadow evidence, and zero direct path to broker mutation or `ApprovedOrder` minting.

**Architecture:** Add a focused `engine/ai/v2/` domain. Reuse the Phase-1 `InternalAdapterRegistry` (`AdapterKind.AI_PROVIDER`) as adapter authority, Data V2 licensing/provenance as data-use authority, `CanonicalCodec` for deterministic evidence, and existing audit conventions. AI providers and agents may emit research evidence / `TradeCandidate` / `NO_TRADE`; they do not own order construction, risk approval, strategy promotion, broker access, Live arming, credentials, or hard-risk configuration.

**Approved spec:** `docs/superpowers/specs/2026-09-27-phase8-ai-research-shadow-design.md`

**Approved decisions:** `docs/v2/phase8/PHASE8_DECISION_FREEZE.md`

**Dependency/branch rule:** Phase 8 depends on Phase 4 + Phase 5, not Phase 6/7. Until Phase-5 PR #8 is merged, create the implementation branch from the current reviewed Phase-5 head (`v2-phase5-paper-recovery`; head observed while writing this plan: `8b2f9849c5cd064d0169ac40601dae6fb62b87fe`). Do **not** modify the Phase-5 branch itself. Bring this design/spec/plan into the Phase-8 implementation branch, then retarget cleanly after Phase 5 merges. If PR #8 head moves before execution, pin and record the new reviewed head before starting.

## Global invariants

- AI authority is `RESEARCH_SHADOW_ONLY`.
- `RiskGateV2` remains the only `ApprovedOrder` mint authority.
- Phase-8 runtime code must not import broker adapters, Live mutation/execution modules, credential/private-key stores, `_mint_approved_order`, or directly construct `ApprovedOrder`.
- `TradeCandidate` is non-executable, immutable, provenance-bearing and TTL-bound.
- `now >= valid_until` means stale: discard as `NO_TRADE` / `HOLD` even when schema is otherwise valid.
- Provider/tool/schema/policy/licensing failures fail closed; no permissive fallback.
- Cloud egress of market/instrument/dataset/research content requires positive Data V2 external-processing licensing/provenance evidence. Redaction never overrides licensing restrictions.
- Runtime agents use the deny-by-default Tool Gateway only; no direct DB/filesystem/broker/network authority outside declared tools/adapters.
- Provider/tool quotas, budgets, timeouts and concurrency limits are explicit/versioned inputs; no guessed production defaults.
- Cloud-provider fallback is explicit-policy-only and must preserve schema, licensing, data policy, redaction, audit, quota and safety.
- Prompt/tool/retrieved content is untrusted data and cannot change permissions, policies, system instructions or risk authority.
- Long-term memory excludes secrets, broker/account identifiers, personal data and raw trade logs.
- Committee/ensemble (`AF2-AIA-008/009`) remains deferred T2.
- Live remains `READ_ONLY / DISARMED`; G8 GREEN does not enable real-money trading.

---

## Task 0 — Baseline, dependency pin and decision-register synchronization

**Read/verify:**
- `ALGOFORTIS_V2_REQUIREMENTS.md`
- `ALGOFORTIS_V2_IMPLEMENTATION_PLAN.md`
- `ALGOFORTIS_V2_OWNER_DECISIONS.md`
- `docs/v2/phase8/PHASE8_DECISION_FREEZE.md`
- `docs/superpowers/specs/2026-09-27-phase8-ai-research-shadow-design.md`
- Phase-5 PR #8 exact head/status
- `engine/core/adapter_registry.py`
- `engine/data/licensing.py`
- `engine/orders/contracts_v2.py`
- `engine/risk/gate_v2.py`
- `engine/reproducibility/codec.py`

**Docs:**
- Modify: `ALGOFORTIS_V2_OWNER_DECISIONS.md`

**Steps:**
1. Pin the exact Phase-5 implementation head used as the Phase-8 code base.
2. Create `v2-phase8-ai-shadow-impl` from that exact Phase-5 head (do not mutate Phase-5 branch).
3. Bring the approved Phase-8 design/spec/plan/freeze docs into the implementation branch.
4. Synchronize the consolidated Owner Decision Register: mark OD-V2-15 and OD-V2-16 FROZEN with the 2026-09-27 decision and Phase-8 freeze/spec references.
5. Verify the blocking matrix shows Phase 8 decisions frozen.
6. Verify no runtime code change exists yet.

**Verification:**
```powershell
python -m pytest tests_v1/test_v2_phase1_adapter_registry.py tests_v1/test_v2_phase3_data_licensing.py -q
```
Expected: existing baseline tests still pass when runnable.

**Commit:** `docs: synchronize Phase 8 owner decisions and dependency pin`

---

## Task 1 — Immutable AI/provider/candidate contracts + Phase-8 static firewall

**Create:**
- `engine/ai/__init__.py`
- `engine/ai/v2/__init__.py`
- `engine/ai/v2/contracts.py`
- `build/tools/check_phase8_ai_shadow.py`
- `tests_v1/test_phase8_ai_contracts.py`
- `tests_v1/test_phase8_ai_architecture_guard.py`

**Core contracts:**
- `ProviderKind = LOCAL | CLOUD`
- `ProviderManifest`
- `AIRequest`
- `AIResponse`
- `ProviderHealth`
- `ProviderUsage`
- `DataClass`
- `TradeCandidateAction = BUY_CE | BUY_PE | HOLD`
- immutable `TradeCandidate`
- `CandidateValidationVerdict` / `NoTradeReason`

**RED tests first:**
1. Invalid/blank provider IDs, versions, model IDs, schema IDs and provenance fail.
2. Naive timestamps fail; candidate `valid_until <= created_at` fails construction.
3. Candidate cannot carry broker order IDs, arming flags, hard-risk overrides, or an `ApprovedOrder` field.
4. Static negative fixtures importing `engine.broker_adapters`, Live mutation/execution, credential/private-key stores, `_mint_approved_order`, or calling `ApprovedOrder(...)` fail the firewall.
5. Static checker rejects direct vendor/network/database calls from pure `engine/ai/v2` domain modules (provider adapter/transport seams are explicitly scoped exceptions).
6. Static checker rejects guessed production provider/quota/data-policy defaults.

**Implement minimum contracts/firewall.**

**Verify:**
```powershell
python -m pytest tests_v1/test_phase8_ai_contracts.py tests_v1/test_phase8_ai_architecture_guard.py -q
python build/tools/check_phase8_ai_shadow.py
```

**Commit:** `feat: add Phase 8 AI contracts and architecture firewall`

---

## Task 2 — Additive Data V2 external-processing licensing evidence + provider data gateway

**Modify (additive, backward-compatible):**
- `engine/data/licensing.py`

**Create:**
- `engine/ai/v2/data_policy.py`
- `engine/ai/v2/provider_gateway.py`
- `tests_v1/test_phase8_data_licensing_egress.py`
- `tests_v1/test_phase8_provider_data_gateway.py`

**Data V2 extension design:**
- Add `ExternalProcessingPermission = ALLOWED | PROHIBITED | UNKNOWN`.
- Add an optional/default-UNKNOWN external-processing permission field to `DataLicenceMetadata` so existing callers remain source-compatible.
- Add a separate fail-closed external-processing decision method/contract (do not silently alter legacy acquisition/use semantics).
- Keep existing `DataLicencePolicy.evaluate(...)` behavior and old Phase-3 tests intact.
- External/cloud-processing decision must bind source ID, licence reference, requested use, external-processing permission, and deterministic fingerprint.

**Gateway pipeline:**
1. classify outbound data classes;
2. resolve source/provenance references;
3. for CLOUD provider requests, require positive Data V2 external-processing permission;
4. enforce provider-specific data-class allowlist;
5. redact/remove forbidden identifiers/secrets;
6. fingerprint sanitized outbound content + licensing decision reference;
7. write safe audit evidence;
8. only then return a provider-ready request.

**RED tests first:**
1. Existing Phase-3 licensing tests still pass unchanged.
2. Missing/UNKNOWN/PROHIBITED external-processing permission blocks cloud egress.
3. Explicit ALLOWED + RESEARCH-permitted metadata can proceed.
4. Redaction cannot convert a licensing-denied payload into allowed egress.
5. Broker credentials/tokens, account IDs, personal data, raw trade logs, private keys and unknown classes are blocked.
6. Secret-canary fixtures never appear in sanitized payload/audit evidence.
7. Missing/stale/ambiguous provenance/licence evidence fails closed.
8. Local-provider processing does not invoke cloud-egress permission but still respects declared dataset use policy.
9. Gateway audit failure blocks dispatch preparation.

**Verify:**
```powershell
python -m pytest tests_v1/test_v2_phase3_data_licensing.py tests_v1/test_phase8_data_licensing_egress.py tests_v1/test_phase8_provider_data_gateway.py -q
python build/tools/check_phase8_ai_shadow.py
```

**Commit:** `feat: gate AI provider data with licensing redaction and provenance`

---

## Task 3 — Reuse Phase-1 adapter registry for AI provider activation/routing/budgets

**Create:**
- `engine/ai/v2/providers.py`
- `engine/ai/v2/routing.py`
- `tests_v1/test_phase8_provider_registry.py`
- `tests_v1/test_phase8_provider_routing.py`

**Design:**
- Use `InternalAdapterRegistry` + `AdapterKind.AI_PROVIDER` as adapter activation authority.
- Contract name: `AIProvider@1` (exact supported contract configured by composition).
- Phase-8 `ProviderManifest` adds AI-specific LOCAL/CLOUD/data-policy/retention/fallback metadata but does not replace the Phase-1 adapter manifest/registry.
- Exactly one configured local route and one configured cloud route for V2.0.
- Provider routing is explicit configuration, never model-selected.
- Health/latency/quota/request-budget/concurrency/timeout are explicit injected policy.

**RED tests first:**
1. Non-`AI_PROVIDER` adapter cannot be routed as an AI provider.
2. Unsupported provider contract/version fails closed.
3. Missing local/cloud route fails the required configuration check.
4. Provider over quota/budget/concurrency/timeout does not dispatch.
5. Unhealthy provider returns research unavailable / `NO_TRADE` unless explicit compatible fallback exists.
6. Unapproved/unknown fallback never activates automatically.
7. Fallback must satisfy same schema/data/licensing/audit policy.
8. Registry activation audit failure prevents provider activation (existing registry invariant preserved).

**Verify:**
```powershell
python -m pytest tests_v1/test_v2_phase1_adapter_registry.py tests_v1/test_phase8_provider_registry.py tests_v1/test_phase8_provider_routing.py -q
```

**Commit:** `feat: route Phase 8 providers through internal adapter registry`

---

## Task 4 — Generic local provider adapter seam (future Laya-compatible)

**Create:**
- `engine/ai/v2/adapters/__init__.py`
- `engine/ai/v2/adapters/local.py`
- `tests_v1/test_phase8_local_provider_adapter.py`

**Design:**
- Generic injected local inference transport/callable; no concrete model dependency required in V2 core.
- No network requirement in the pure local adapter contract.
- Output must be structured `AIResponse`, schema/version/provenance checked.
- Adapter cannot reach broker/Live/risk/promotion modules.
- Future Laya-compatible local runtime binds behind this seam without changing candidate/tool/risk safety.

**RED tests first:**
1. Missing local transport fails closed; no fake-success response.
2. Malformed provider output rejected.
3. Wrong schema/version rejected.
4. Timeout/transport exception becomes provider-unavailable evidence, not candidate approval.
5. Input/output fingerprints deterministic for same structured evidence.

**Verify:**
```powershell
python -m pytest tests_v1/test_phase8_local_provider_adapter.py -q
python build/tools/check_phase8_ai_shadow.py
```

**Commit:** `feat: add model-agnostic local AI provider seam`

---

## Task 5 — Generic cloud provider adapter seam with mandatory gateway

**Create:**
- `engine/ai/v2/adapters/cloud.py`
- `tests_v1/test_phase8_cloud_provider_adapter.py`

**Design:**
- Vendor-neutral injected cloud transport. Do not bind a concrete paid/cloud provider in core until separately configured.
- Adapter accepts only a gateway-approved provider request/evidence object; raw unclassified payload is not accepted.
- No direct cloud call may bypass `ProviderDataGateway`.
- Safe output schema validation before response returns to orchestration.

**RED tests first:**
1. Raw/unclassified request cannot be dispatched.
2. Missing licensing decision blocks cloud transport invocation.
3. Denied data class/redaction/licence decision proves transport was never called.
4. Gateway-approved request dispatches exactly once.
5. Provider timeout/malformed output -> unavailable/`NO_TRADE`, not fallback execution.
6. Audit metadata contains fingerprints/policy refs but not raw secrets/sensitive payloads.

**Verify:**
```powershell
python -m pytest tests_v1/test_phase8_cloud_provider_adapter.py tests_v1/test_phase8_provider_data_gateway.py -q
```

**Commit:** `feat: add gateway-only cloud AI provider seam`

---

## Task 6 — Deterministic TradeCandidate validator with hard TTL discard

**Create:**
- `engine/ai/v2/candidates.py`
- `tests_v1/test_phase8_trade_candidate_validator.py`

**Interfaces:**
- `TradeCandidateValidator(clock, policy)`
- `validate(candidate) -> CandidateValidationVerdict`

**RED tests first:**
1. `now >= valid_until` rejects as `STALE_CANDIDATE` and maps to `NO_TRADE/HOLD`.
2. An otherwise perfectly valid expired candidate is still rejected.
3. Unsupported action vocabulary rejects.
4. Missing provider/model/agent/schema/provenance/input fingerprint rejects.
5. Missing/stale input-data freshness marker rejects.
6. Instrument scope incompatible with current options-BUY-only research policy rejects.
7. `BUY_CE` / `BUY_PE` are research hypotheses only and never construct `OrderIntent` or `ApprovedOrder`.
8. Same candidate/policy/time evidence produces deterministic verdict fingerprint.

**Verify:**
```powershell
python -m pytest tests_v1/test_phase8_trade_candidate_validator.py -q
python build/tools/check_phase8_ai_shadow.py
```

**Commit:** `feat: add deterministic TTL-bound TradeCandidate validation`

---

## Task 7 — Deny-by-default Tool Gateway with scope/rate/budget/audit enforcement

**Create:**
- `engine/ai/v2/tool_gateway.py`
- `tests_v1/test_phase8_tool_gateway.py`

**Contracts:**
- `ToolManifest`
- `ToolInvocation`
- `ToolPolicy`
- `ToolDecision`
- `ToolGateway`

**RED tests first:**
1. Unknown/unregistered tool denied.
2. Tool not on agent allowlist denied.
3. Read/write classification mismatch denied.
4. Path/data-scope escape denied (including `..`, alternate separators, symlink-resolution contract via injected resolver where applicable).
5. Rate/quota/budget/concurrency excess denied before dispatch.
6. Audit-before-dispatch failure blocks tool call.
7. Research artifact write tool can write only approved artifact area via injected tool implementation.
8. Broker/Live/credentials/risk-limit/kill-switch/promotion tools cannot be registered as Phase-8 runtime tools.
9. Tool output is classified/sanitized before becoming provider input.

**Verify:**
```powershell
python -m pytest tests_v1/test_phase8_tool_gateway.py -q
python build/tools/check_phase8_ai_shadow.py
```

**Commit:** `feat: add deny-by-default AI tool gateway`

---

## Task 8 — Prime/Research/Risk-Challenger orchestration

**Create:**
- `engine/ai/v2/agents.py`
- `engine/ai/v2/orchestrator.py`
- `tests_v1/test_phase8_agent_orchestration.py`

**Roles:**
- `PrimeRouter`: routes approved research tasks/evidence only.
- `ResearchAgent`: creates hypotheses/candidates.
- `RiskChallenger`: may challenge/veto; cannot approve/mint/widen risk.

**RED tests first:**
1. Only approved three V2.0 roles exist; committee/ensemble is absent/deferred.
2. Risk challenger can veto to `NO_TRADE` but cannot turn HOLD/rejection into approval.
3. Material unresolved disagreement => `NO_TRADE`.
4. Agent cannot select provider/tool outside routing/policy configuration.
5. Agent cannot self-promote strategy/model or alter risk limits.
6. Candidate must pass deterministic validator after agent output.
7. Orchestrator contains no order/broker execution path.

**Verify:**
```powershell
python -m pytest tests_v1/test_phase8_agent_orchestration.py -q
python build/tools/check_phase8_ai_shadow.py
```

**Commit:** `feat: add minimal Phase 8 research agent orchestration`

---

## Task 9 — Untrusted-content / prompt-injection boundary + market-intelligence scheduler

**Create:**
- `engine/ai/v2/untrusted.py`
- `engine/ai/v2/scheduler.py`
- `tests_v1/test_phase8_prompt_injection.py`
- `tests_v1/test_phase8_market_intelligence_scheduler.py`

**RED prompt-injection tests:**
1. Retrieved content saying “ignore policy/system instructions” remains inert untrusted text.
2. Model/tool output cannot add tool permissions or invent tool IDs/paths/commands.
3. URLs/content retain provenance labels and normalization.
4. Suspicious content can be quarantined/NO_TRADE without changing policy state.
5. Embedded secret-exfiltration instruction cannot bypass provider data gateway.

**RED scheduler tests:**
1. Injected clock only; no hidden wall-clock decision semantics.
2. Bounded queue/concurrency enforced.
3. Provider/tool budget exhaustion pauses/rejects research job, does not expand budget.
4. Stale input data -> research unavailable / NO_TRADE.
5. Scheduler accepts research/shadow jobs only; broker/order actions structurally unsupported.

**Verify:**
```powershell
python -m pytest tests_v1/test_phase8_prompt_injection.py tests_v1/test_phase8_market_intelligence_scheduler.py -q
```

**Commit:** `feat: add untrusted-content boundary and bounded AI scheduler`

---

## Task 10 — Per-user long-term memory boundary

**Create:**
- `engine/ai/v2/memory.py`
- `tests_v1/test_phase8_ai_memory.py`

**Design:**
- Memory is an injected persistence port/domain contract, not direct DB access.
- Only approved non-secret long-term facts with source/provenance/policy version.
- Correction/deletion supported.

**RED tests first:**
1. Cross-user read/write isolation enforced.
2. Secret/token/private-key/broker-account/raw-trade-log/personal-identity classes rejected.
3. Missing provenance or data classification rejected.
4. Correction creates auditable versioned replacement semantics.
5. Deletion/revocation removes item from active retrieval without leaking payload into audit.
6. Provider output cannot directly persist memory without policy validation.

**Verify:**
```powershell
python -m pytest tests_v1/test_phase8_ai_memory.py -q
```

**Commit:** `feat: add policy-bound Phase 8 agent memory`

---

## Task 11 — Shadow-mode decision log + outcome evaluation

**Create:**
- `engine/ai/v2/shadow.py`
- `tests_v1/test_phase8_shadow_mode.py`

**Shadow record:**
- candidate or NO_TRADE result;
- provider/model/agent versions;
- input/evidence fingerprints;
- validator verdict;
- challenger verdict;
- timestamp/TTL;
- policy/licensing references;
- later outcome evaluation when available;
- calibration/quality metrics;
- audit/replay references.

**RED tests first:**
1. Shadow path never constructs/submits an order.
2. Stale candidate is recorded as rejected/NO_TRADE, never as an active recommendation.
3. Same safe evidence -> deterministic shadow record identity.
4. Later outcome can be attached without rewriting original decision evidence.
5. Shadow metrics cannot auto-promote model/strategy or change provider routing.
6. Missing core provenance/licensing/policy evidence blocks shadow “valid” classification.

**Verify:**
```powershell
python -m pytest tests_v1/test_phase8_shadow_mode.py -q
python build/tools/check_phase8_ai_shadow.py
```

**Commit:** `feat: add non-executable AI shadow evaluation log`

---

## Task 12 — AI audit/replay + provider outage/fallback behavior

**Create:**
- `engine/ai/v2/audit.py`
- `engine/ai/v2/replay.py`
- `tests_v1/test_phase8_ai_audit_replay.py`
- `tests_v1/test_phase8_provider_outage.py`

**Design:**
- Reuse existing audit envelope/sink conventions via a narrow injected AI audit sink; do not create a competing global audit authority.
- Persist safe metadata/fingerprints/policy references, never forbidden raw sensitive payloads.

**RED tests first:**
1. Audit failure blocks policy-sensitive provider/tool action when evidence is required.
2. Audit output contains provider/model/tool/policy/licensing/correlation/fingerprint refs.
3. Audit output excludes canary secrets, account IDs, personal data and raw trade logs.
4. Replay reconstructs decision chain from safe evidence without credentials/broker/Live access.
5. Provider outage -> explicit compatible fallback only; otherwise NO_TRADE/research unavailable.
6. Fallback cannot bypass gateway/licensing/redaction/quota/audit/schema requirements.
7. Replay cannot create an order or alter prior evidence.

**Verify:**
```powershell
python -m pytest tests_v1/test_phase8_ai_audit_replay.py tests_v1/test_phase8_provider_outage.py -q
```

**Commit:** `feat: add AI audit replay and fail-closed provider fallback`

---

## Task 13 — Deterministic G8 evidence + qualification workflow

**Create:**
- `engine/ai/v2/evidence.py`
- `build/tools/phase8_ai_probe.py`
- `tests_v1/test_phase8_ai_evidence.py`
- `tests_v1/test_phase8_ai_qualification_guard.py`
- `.github/workflows/v2-phase8-ai-shadow.yml`

**Extend:**
- `build/tools/check_phase8_ai_shadow.py`

**Required deterministic markers:**
- `AI_AUTHORITY=RESEARCH_SHADOW_ONLY`
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

**RED tests first:**
1. Evidence fails if any authority/safety/licensing/TTL/tool marker disappears.
2. Qualification guard fails if focused tests/static guard/probe/workflow/compare job disappear.
3. Static guard requires all Phase-8 authority modules/tests/evidence.

**Workflow:**
- Windows latest / Python 3.13.14
- Windows 2022 / Python 3.13.14
- locked dependencies
- Phase-8 static firewall
- all Phase-8 focused tests
- relevant Phase-1 adapter registry + Phase-3 data licensing regression tests
- deterministic probe artifact from each Windows leg
- Ubuntu compare job normalizes CRLF only and requires byte-identical evidence/markers

**Local verification command:**
```powershell
python -m pytest tests_v1/test_phase8_*.py tests_v1/test_v2_phase1_adapter_registry.py tests_v1/test_v2_phase3_data_licensing.py -q
python build/tools/check_phase8_ai_shadow.py
python build/tools/phase8_ai_probe.py
```

Do **not** claim G8 GREEN from local success alone.

**Commit:** `ci: add deterministic G8 AI shadow qualification`

---

## Task 14 — G8 evidence record and final Phase-8 review

**Create:**
- `docs/v2/phase8/G8_EVIDENCE.md`

**Record:**
- exact implementation head;
- Phase-5 dependency head used;
- focused test count/result;
- static firewall result;
- deterministic probe fingerprint;
- hosted workflow/run/job IDs;
- Windows latest/2022 step execution status;
- cross-Windows compare result;
- external blocker if jobs fail before steps;
- explicit statement: G8 does not authorize real-money trading; Live remains `READ_ONLY / DISARMED`.

**Final review checklist:**
1. AF2-AIA-001…007 and AIA-010 mapped to tests/evidence.
2. AIA-008/009 absent/deferred, not accidentally implemented.
3. No Phase-8 module can mint `ApprovedOrder` or reach broker/Live mutation.
4. Candidate TTL expiry is a hard discard.
5. Tool Gateway is mandatory for runtime agent tool access.
6. Cloud egress requires positive licensing/provenance evidence.
7. Provider outage/fallback cannot loosen safety.
8. Shadow mode never places orders or auto-promotes.
9. Existing Phase-1 registry, Phase-3 licensing, Phase-4/5 dependent regressions remain preserved.
10. Hosted G8 status is reported exactly; `steps=null`/pre-provisioning failure is neither GREEN nor code RED.

**Verification before any completion claim:**
```powershell
python -m pytest tests_v1/test_phase8_*.py tests_v1/test_v2_phase1_adapter_registry.py tests_v1/test_v2_phase3_data_licensing.py -q
python build/tools/check_phase8_ai_shadow.py
python build/tools/phase8_ai_probe.py
```
Then inspect exact hosted workflow jobs/steps and compare evidence.

**Commit:** `docs: record G8 AI shadow qualification evidence`

---

## Requirement mapping

- **AF2-AIA-001 advisory/no bypass:** Tasks 1, 6, 7, 8, 11, 13.
- **AF2-AIA-002 provider abstraction/local+cloud/health/quota/fallback:** Tasks 2–5, 12.
- **AF2-AIA-003 TradeCandidate contract:** Tasks 1 + 6.
- **AF2-AIA-004 continuous intelligence + untrusted content:** Task 9.
- **AF2-AIA-005 tool/capability safety:** Tasks 1 + 7 + 9 + 13.
- **AF2-AIA-006 memory:** Task 10.
- **AF2-AIA-007 shadow mode:** Task 11.
- **AF2-AIA-010 build-time agent governance:** this task-by-task TDD plan + existing project slice/verification protocol; runtime Tool Gateway is intentionally separate.
- **OD-V2-15:** one local + one cloud seam, research/shadow only, committee deferred.
- **OD-V2-16:** provider data allowlist/redaction + explicit cloud licensing/provenance egress gate.

## Explicit non-goals

- no autonomous Live execution;
- no AI-generated broker command;
- no AI hard-risk/kill-switch control;
- no AI self-promotion;
- no committee/ensemble voting;
- no unrestricted shell/filesystem/network/database access;
- no concrete cloud-provider dependency required by core;
- no actual Laya model/runtime integration yet—only the model-agnostic local provider seam;
- no assumption that G8 GREEN changes Live state.
