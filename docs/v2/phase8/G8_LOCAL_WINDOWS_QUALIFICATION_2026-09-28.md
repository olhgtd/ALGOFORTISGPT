# Phase 8 Local Windows Qualification Evidence — 2026-09-28

## Scope

This document records fresh local Windows qualification evidence for the Phase 8 AI / Agents Research + Shadow implementation.

Tested branch:

`v2-phase8-ai-shadow-impl`

Tested code head:

`93860a2a9bc28800dbaf1230c4399a8c1b240acf`

Environment observed during the run:

- Windows PowerShell
- Python 3.13.14 environment already prepared for the repository
- short pytest temp root mapped to `T:\`
- `PYTHONPATH` set to repository root

This is local Windows evidence only. It does not replace required hosted exact-head dual-Windows G8 qualification.

## Fresh observed results

### Targeted shadow-mode regression

- `tests_v1/test_phase8_shadow_mode.py`: `5 passed`

The stale test expectation was aligned with the stronger contract invariant that `TradeCandidate.provenance_refs` must be non-empty at construction time. Production safety logic was not weakened.

### Static firewall

Observed markers:

```text
PHASE8_FIREWALL=PASS
G8_QUALIFICATION_ARTIFACTS=PASS
AI_AUTHORITY=RESEARCH_SHADOW_ONLY
LIVE_STATE=READ_ONLY/DISARMED
```

### Focused Phase 8 + dependency suite

- result: `94 passed`

The suite included all `test_phase8_*.py` tests plus the Phase-1 adapter registry and Phase-3 data-licensing dependency regressions.

### Deterministic G8 probe

Two consecutive local probe outputs were byte-identical.

Observed markers:

```text
AI_AUTHORITY=RESEARCH_SHADOW_ONLY
APPROVED_ORDER_AUTHORITY=RISK_GATE_V2_ONLY
PROVIDER_SCOPE=ONE_LOCAL_ONE_CLOUD
COMMITTEE_ENSEMBLE=DEFERRED_T2
PROVIDER_DATA_GATE=ALLOWLIST_REDACT_FAIL_CLOSED
CLOUD_DATA_EGRESS=LICENSING_PROVENANCE_REQUIRED
TRADE_CANDIDATE=NON_EXECUTABLE_TTL_PROVENANCE
STALE_CANDIDATE=DISCARD_NO_TRADE
TOOL_GATEWAY=DENY_BY_DEFAULT_QUOTA_AUDIT
PROMPT_INJECTION=UNTRUSTED_CONTENT_BOUNDARY
PROVIDER_OUTAGE=NO_TRADE_OR_APPROVED_FALLBACK
LIVE_STATE=READ_ONLY/DISARMED
G8_ENABLES_REAL_MONEY_TRADING=NO
G8_FINGERPRINT=56879e50a0e76e70a31f71667df3df8a17f517b6abc8e0002ee457cec4bc78e1
```

### Full project regression

- result: `624 passed, 1 warning`
- warning: Starlette TestClient / AnyIO BlockingPortal deprecation warning; not a test failure

### Regression certification

- self-contained architectural tests: `13` passed
- final output: `=== REGRESSION VERIFICATION: ALL PASS ===`

## Safety assertions supported by the run

- `AI_AUTHORITY=RESEARCH_SHADOW_ONLY`
- `APPROVED_ORDER_AUTHORITY=RISK_GATE_V2_ONLY`
- `LIVE_STATE=READ_ONLY/DISARMED`
- `G8_ENABLES_REAL_MONEY_TRADING=NO`
- cloud egress remains gated by licensing/provenance evidence
- TradeCandidate remains non-executable, TTL-bound, and provenance-bearing
- Tool Gateway remains deny-by-default
- prompt-injection content remains untrusted data
- provider outage fails closed to NO_TRADE or approved compatible fallback

## Qualification status

Local Windows qualification for tested code head `93860a2a9bc28800dbaf1230c4399a8c1b240acf` is GREEN.

Formal G8 remains **NOT QUALIFIED** until fresh hosted exact-head qualification executes successfully on both required Windows environments and the cross-Windows deterministic comparison job passes. GitHub-hosted Actions quota is currently exhausted, so that external evidence gate is deferred until quota reset.
