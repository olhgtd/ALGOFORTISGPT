# AlgoFortis V2 — Phase 8 AI / Agents Research + Shadow Design

**Date:** 2026-09-27  
**Status:** OWNER-DIRECTION FROZEN; SPEC FOR OWNER REVIEW  
**Scope:** AF2-AIA-001…007, AF2-AIA-010; G8  
**Deferred:** AF2-AIA-008/009 committee/ensemble/full role catalogue remain T2  
**Standing state:** Live remains `READ_ONLY / DISARMED`

## 1. Owner decisions frozen for Phase 8

### OD-V2-15 — AI scope/provider set

V2.0 Phase 8 is **Research + Shadow only**.

- one local provider path;
- one cloud provider path;
- both behind the same versioned provider contract/registry;
- provider routing is configuration/policy driven;
- committee/ensemble remains deferred T2 scope;
- no provider or agent receives execution authority.

### OD-V2-16 — data-sharing boundary

AI/provider access is controlled by an explicit versioned data-class allowlist plus mandatory redaction.

Never send to any AI provider:

- broker credentials or tokens;
- broker/account identifiers;
- personal identity data;
- raw trade logs;
- device-binding/private-key material;
- secrets from config/environment/secrets stores;
- any data class not explicitly allowed by the active provider policy.

Cloud calls fail closed when data classification, allowlist, redaction, provider-retention evidence, or required external-use licensing/provenance evidence is missing/unavailable.

**Market/instrument data licensing boundary:** before market, instrument, dataset-derived, news-derived, or research data leaves the local machine for a cloud AI provider, Phase 8 must verify the authoritative Data V2 provenance/licensing policy permits that external/provider use. Redaction does not make otherwise restricted data exportable. Missing, stale, ambiguous, or prohibitive licensing/provenance evidence blocks the outbound call fail-closed. Local-provider processing remains subject to the dataset's own usage policy but does not create cloud egress.

## 2. Phase-8 goal

Build a useful AI research/shadow subsystem that can:

- analyze approved market/research inputs;
- generate structured hypotheses and `TradeCandidate` values;
- run research and shadow evaluation;
- use permissioned research tools through a gateway;
- retain auditable, provenance-bearing evidence;
- compare shadow decisions with later outcomes;
- degrade safely on provider/tool/schema/policy failure;

while proving there is **no path from AI output to broker mutation or an `ApprovedOrder` except through deterministic strategy/rule validation and the existing central `RiskGateV2`**.

## 3. Standing safety invariants

1. AI is advisory/research/shadow only.
2. No Phase-8 module may import broker adapters, Live execution/mutation modules, credential stores, `_mint_approved_order`, or construct `ApprovedOrder`.
3. AI cannot arm Live, alter hard risk limits, modify kill switches, promote a strategy, or bypass normal strategy/promotion/risk lifecycle.
4. `TradeCandidate` is **not executable**. It is TTL-bound, provenance-bearing evidence only.
5. Candidate validation is deterministic and model-independent.
6. Malformed, stale, expired-TTL, ambiguous, policy-violating, unsupported, or unavailable AI output becomes `NO_TRADE` / `HOLD`; an expired candidate is discarded even if its schema is otherwise valid.
7. Provider fallback is allowed only when explicitly policy-approved and must preserve schema, data-sharing rules, audit, budgets, licensing/provenance policy, and safety.
8. Provider/tool outage never creates a permissive default or execution fallback.
9. Retrieved web/news/tool content is untrusted data. It never changes system instructions, tool permissions, policy, or risk authority.
10. Agent/tool actions are deny-by-default and allowlist-scoped through the Tool Gateway; declared scope, rate/budget controls, and per-call audit evidence are mandatory.
11. Long-term agent memory stores only approved non-secret facts with provenance; no credentials, personal data, account identifiers, or raw trade logs.
12. Any cloud egress of market/instrument/dataset-derived content requires positive Data V2 licensing/provenance evidence permitting external/provider use; unknown or restricted policy blocks the call.
13. Live remains `READ_ONLY / DISARMED`; G8 GREEN does not authorize real-money trading.

## 4. Architecture

### 4.1 New Phase-8 AI domain

Create focused modules under `engine/ai/v2/`.

It owns:

- provider contracts and manifests;
- provider registry/routing policy;
- data classification + provider allowlist policy;
- Data V2 licensing/provenance egress policy check;
- deterministic redaction gateway;
- AI request/response envelope;
- `TradeCandidate` / `NO_TRADE` contract;
- deterministic candidate validator;
- permissioned tool-gateway contracts;
- research/shadow agent orchestration;
- shadow-decision log/evaluation contracts;
- provider/tool health, quotas and budgets;
- AI action/audit/replay evidence;
- deterministic G8 evidence.

It does **not** own:

- broker communication;
- order construction/submission;
- risk approval;
- Live arming;
- hard-risk configuration;
- strategy promotion;
- broker/account secrets.

### 4.2 Provider contract and registry

Define a versioned provider contract such as:

- `ProviderManifest`
- `AIRequest`
- `AIResponse`
- `ProviderHealth`
- `ProviderUsage`
- `AIProvider.generate(request) -> AIResponse`

Provider manifest declares:

- provider ID/version;
- local vs cloud classification;
- supported structured schemas/capabilities;
- data classes accepted by policy;
- retention/policy evidence reference where required;
- latency/quota/cost telemetry capability;
- fallback eligibility.

The internal adapter registry from Phase 1 remains the registry authority; Phase 8 does not create a parallel plugin system.

V2.0 includes exactly two provider seams: one local adapter and one cloud adapter. Concrete model choice remains configuration, so a future local Laya-compatible adapter can bind behind the same contract without changing AI safety or trading authority.

### 4.3 Provider data + licensing gateway

All provider-bound content passes through one policy gateway before provider code sees it. Cloud-bound market/instrument/dataset-derived content additionally requires positive Data V2 external-use licensing/provenance evidence before egress.

Pipeline:

1. classify data into versioned data classes;
2. resolve source dataset/content provenance where licensing policy applies;
3. for cloud egress, verify the authoritative Data V2 licensing policy explicitly permits external/provider use;
4. check provider-specific allowlist;
5. redact/remove forbidden identifiers/secrets;
6. produce a deterministic outbound-content fingerprint plus licensing-policy evidence reference;
7. write safe audit evidence;
8. only then call the provider.

Missing classifier, missing provider policy, unknown data class, redaction failure, missing/stale/ambiguous licensing evidence, or a policy that forbids external/provider use causes fail-closed rejection.

Redaction is not a licensing override: data that is contractually/policy restricted from external processing stays local even after identifiers are removed.

The gateway must be independently testable with secret canaries, licensing-denial fixtures, stale/missing provenance fixtures, and negative data-class fixtures.

### 4.4 `TradeCandidate` contract

`TradeCandidate` is immutable and structured. Minimum fields:

- candidate ID;
- strategy/research context reference;
- concrete instrument reference;
- directional hypothesis (`BUY_CE`, `BUY_PE`, `HOLD` or normalized research action vocabulary compatible with current options-BUY-only scope);
- confidence/calibration evidence if supplied by the provider;
- created timestamp and strict `valid_until` TTL;
- input/evidence fingerprint;
- provider/model/agent versions;
- rationale/evidence references safe for audit;
- schema version.

It explicitly excludes:

- broker order IDs;
- `ApprovedOrder`;
- broker mutation methods;
- arming flags;
- hard-risk overrides;
- direct executable quantity authority unless a later deterministic strategy rule derives/validates it through the normal path.

The deterministic validator checks schema, TTL, instrument scope, allowed action vocabulary, provenance completeness, data freshness/policy markers, and required evidence. `now >= valid_until` is a hard stale-candidate rejection even when all other fields are valid. Invalid or expired candidate => discard as `NO_TRADE` / `HOLD`.

### 4.5 Deterministic strategy/risk boundary

AI never becomes a second strategy/execution authority.

Safe flow:

`approved data/research -> AI provider/agent -> TradeCandidate -> deterministic candidate validator -> deterministic strategy/rule layer -> existing OrderIntent -> existing RiskGateV2 -> (paper/shadow evidence in Phase 8; no Live mutation)`

Phase-8 code cannot import or call the private approval mint. A static architecture guard must prove this.

### 4.6 Tool gateway

Agents act only through a deny-by-default Tool Gateway; runtime agents never receive direct DB/filesystem/broker/network authority outside declared gateway tools.

Each tool manifest declares:

- stable tool ID/version;
- read/write classification;
- allowed path/data scope;
- input/output schema;
- maximum invocation budget/rate;
- side-effect class;
- audit requirements.

Every tool invocation must pass capability/scope validation, rate/quota/budget enforcement, and per-call audit evidence before dispatch. Tool failure or missing enforcement evidence fails closed.

Phase-8 research/shadow default tools are read-only wherever practical. Any write-capable research artifact tool must be scoped to approved research/artifact locations and can never reach broker, Live, credentials, risk-limit, kill-switch, or promotion authority.

Shell/command execution is not a general runtime AI privilege. Build-time coding-agent governance remains AF2-AIA-010 and uses existing slice/verification controls rather than the runtime research-agent permission set.

### 4.7 Initial agents

V2.0 starts with the smallest useful set:

- **Prime/Router:** routes approved research tasks and composes evidence; no execution authority.
- **Research Agent:** market/strategy research and hypothesis generation.
- **Risk Challenger:** challenges candidate assumptions and may veto to `NO_TRADE`; cannot approve an order or widen risk.

This is not a committee/ensemble implementation. Disagreement handling is conservative: unresolved material disagreement => `NO_TRADE` / research-only output.

### 4.8 Market intelligence scheduler

Scheduler may run research jobs on approved data cadence and store shadow/research evidence.

It must:

- use injected clock/time sources;
- have bounded queues/concurrency;
- respect provider/tool budgets;
- stop/degrade on stale data;
- never schedule broker/order actions;
- never convert a research result directly into an executable order.

### 4.9 Prompt-injection and untrusted-content boundary

External/retrieved content is wrapped and labelled as untrusted evidence.

Rules:

- content cannot alter system/developer/tool policies;
- instructions embedded in retrieved content are never treated as agent instructions;
- no dynamic tool permission expansion from model output;
- provider output cannot create arbitrary tool names/paths/commands;
- URLs/content are normalized and provenance-captured;
- suspicious/malformed content may be quarantined or converted to `NO_TRADE` / research-only evidence;
- adversarial fixtures are mandatory in G8.

### 4.10 Memory

Memory is scoped per user/research profile and stores only explicitly approved long-term facts.

Every stored memory item includes:

- stable identity;
- provenance/source;
- created/updated timestamp;
- data class;
- correction/deletion support;
- policy version.

Forbidden memory content includes secrets, account/broker identifiers, personal identity data, raw trade logs, private keys/tokens, or unrestricted copied web content.

### 4.11 Shadow mode

Shadow mode records what the AI would have suggested without creating an order.

Each shadow record includes:

- candidate/NO_TRADE output;
- provider/model/agent versions;
- inputs/evidence fingerprints;
- candidate-validation verdict;
- risk-challenger verdict;
- timestamp/TTL;
- later observed outcome/evaluation where available;
- calibration/quality metrics;
- full audit/replay references.

Shadow evaluation cannot silently promote a strategy or model. Any later paper eligibility follows the existing strategy lifecycle/promotion system and requires explicit evidence.

### 4.12 Budgets/quotas/provider outage

Provider policy supplies explicit versioned limits for:

- request count;
- token/compute budget where measurable;
- concurrency;
- timeout;
- approved fallback chain.

No guessed production budget is embedded in source.

Provider and Tool Gateway quota/budget enforcement is deny-by-default and auditable per call/request. A request with missing budget/quota policy or unavailable usage evidence fails closed rather than exceeding an unknown limit.

If the chosen provider is unavailable:

- use only an explicitly approved compatible fallback;
- otherwise return `NO_TRADE` / research-unavailable;
- never skip schema/data-policy/licensing/audit checks;
- never switch to an unknown provider automatically.

## 5. Audit and replay

Every AI/provider/tool/agent decision uses the existing audit envelope conventions and includes where applicable:

- user/research/run/correlation IDs;
- agent/provider/model/tool versions;
- policy/data-class/redaction versions;
- licensing/provenance policy/evidence reference for provider-bound market/instrument/dataset content;
- input/output fingerprints;
- candidate/validator/shadow verdict;
- quota/latency/health evidence;
- failure/fallback reason;
- timestamps and deterministic sequence evidence.

Audit stores safe metadata/fingerprints rather than forbidden raw secret/sensitive payloads.

A replay path reconstructs the decision chain from stored safe evidence without requiring broker credentials or direct Live access.

## 6. Static architecture firewall

Create `build/tools/check_phase8_ai_shadow.py` that rejects Phase-8 runtime code if it:

- imports broker adapters or Live mutation modules;
- imports `_mint_approved_order`;
- constructs/calls `ApprovedOrder`;
- imports credential/private-key stores;
- writes risk hard limits, kill-switch authority, or promotion authority;
- contains direct network/vendor calls in pure domain modules rather than provider adapters;
- embeds unapproved production provider/budget/data-sharing defaults;
- bypasses the provider data/licensing gateway for cloud adapters.

The checker also requires Phase-8 focused tests, G8 probe, evidence doc, and workflow once those artifacts exist.

## 7. G8 qualification evidence

G8 must prove at minimum:

1. AI output has no direct order/broker path.
2. `TradeCandidate` is non-executable and TTL/provenance validated; a well-formed but expired candidate is discarded to `NO_TRADE` / `HOLD`.
3. No-bypass tests prove only deterministic rules + existing `RiskGateV2` can lead toward an executable order contract.
4. Provider data gateway blocks secrets/account IDs/personal data/raw trade logs and unknown data classes.
5. Cloud-provider egress tests prove market/instrument/dataset-derived content is blocked when Data V2 licensing/provenance evidence is missing, stale, ambiguous, or prohibits external/provider processing; redaction cannot bypass that denial.
6. Prompt-injection/adversarial retrieved-content suite cannot expand permissions or cause policy/tool changes.
7. Provider outage degrades to `NO_TRADE` unless an explicitly approved compatible fallback is available.
8. Tool Gateway deny-by-default, read/write/path/data allowlists, per-call rate/budget/quota enforcement, and per-call audit evidence are enforced.
9. Memory isolation/secret exclusion tests pass.
10. Shadow logs are deterministic, auditable and accumulating without order placement.
11. Deterministic G8 evidence matches across required environments when hosted runners are available.

Suggested deterministic markers:

- `AI_AUTHORITY=RESEARCH_SHADOW_ONLY`
- `APPROVED_ORDER_AUTHORITY=RISK_GATE_V2_ONLY`
- `PROVIDER_SCOPE=ONE_LOCAL_ONE_CLOUD`
- `COMMITTEE_ENSEMBLE=DEFERRED_T2`
- `PROVIDER_DATA_GATE=ALLOWLIST_REDACT_FAIL_CLOSED`
- `CLOUD_DATA_EGRESS=LICENSING_PROVENANCE_GATED`
- `TRADE_CANDIDATE=NON_EXECUTABLE_TTL_PROVENANCE`
- `STALE_CANDIDATE=DISCARD_NO_TRADE`
- `TOOL_GATEWAY=DENY_DEFAULT_QUOTA_AUDIT_PER_CALL`
- `PROMPT_INJECTION=UNTRUSTED_CONTENT_BOUNDARY`
- `PROVIDER_OUTAGE=NO_TRADE_OR_APPROVED_FALLBACK`
- `LIVE_STATE=READ_ONLY/DISARMED`
- `G8_ENABLES_REAL_MONEY_TRADING=NO`

## 8. Implementation sequencing after spec approval

After Owner reviews this written spec, the implementation plan should be split into small TDD slices in this order:

1. immutable AI/provider/data-class/candidate contracts + static firewall;
2. data classification/redaction/Data V2 licensing-provenance/provider-policy gateway;
3. provider registry/routing/health/budget/quota contracts;
4. local provider adapter seam;
5. cloud provider adapter seam using the same data/licensing gateway;
6. deterministic `TradeCandidate` validator including strict TTL-expiry rejection;
7. deny-by-default Tool Gateway with per-call scope/quota/budget/audit enforcement;
8. Prime/Research/Risk-challenger orchestration;
9. prompt-injection/untrusted-content defenses;
10. memory boundary;
11. shadow log/outcome evaluation;
12. audit/replay + provider outage/fallback tests;
13. deterministic G8 evidence/workflow/evidence record.

## 9. Non-goals / explicitly deferred

- multi-agent committee/ensemble voting;
- 3–5+ model consensus engines;
- direct AI broker/order execution;
- AI-controlled hard-risk or kill-switch settings;
- AI strategy promotion;
- autonomous Live arming;
- unrestricted shell/filesystem/network access;
- cloud storage of broker credentials/account identifiers/raw trade logs;
- cloud-provider export of market/instrument/dataset content without positive external-use licensing/provenance evidence;
- any assumption that G8 GREEN enables Live trading.

## 10. Final invariant

**Phase 8 is useful AI research + shadow capability, not an autonomous trading authority. G8 GREEN does not enable broker mutation or real-money trading. Live remains `READ_ONLY / DISARMED`.**
