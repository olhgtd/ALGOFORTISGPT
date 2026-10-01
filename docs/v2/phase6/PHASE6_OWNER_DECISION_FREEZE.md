# AlgoFortis V2 Phase 6 — Owner Decision Freeze

**Date:** 2026-09-26  
**Status:** FROZEN  
**Phase:** Phase 6 — Live Execution V2 (still DISARMED)  
**Authority:** Owner approval recorded on 2026-09-26; formalized by `docs/v2/adr/ADR-015-phase6-live-safety-policy.md`.

## Frozen decisions

| Decision | Frozen choice | Binding outcome |
|---|---|---|
| OD-V2-05 | A | Local hard backstop for Live exclusivity; cloud cannot be trading authority. |
| OD-V2-06 | A | Foreign broker activity halts new entries + alerts; manual adoption only; never ignore/auto-adopt. |
| OD-V2-08 | A | Broker-resident protection mandatory where supported; unsupported required protection keeps the affected Live path DISARMED pending separate degraded-policy approval. |
| OD-V2-09 | A | Dated current broker/exchange/regulatory verification mandatory before G6 exit; old assumptions are insufficient. |

## Standing constraints

- Live remains `READ_ONLY / DISARMED`.
- This freeze authorizes Phase-6 design and DISARMED/read-only qualification work only.
- It does not authorize real-money execution.
- S2 device/session gating remains required before Phase-6 exit.
- RiskGate remains the executable-order approval authority.
- Restart/reconnect never auto-arms.
- Foreign activity and uncertainty fail closed.
- Any change to these four decisions requires a new dated Owner Decision/ADR entry; no silent edits.
