# AlgoFortis V2 Phase 5 — Owner Decision Freeze

**Date:** 2026-09-25  
**Status:** OWNER-FROZEN  
**Scope:** Phase 5 entry blockers only

This addendum records the Owner approvals that unblock Phase 5 design work. It supplements `ALGOFORTIS_V2_OWNER_DECISIONS.md`; where that older register still shows these two entries as OPEN, this dated addendum is the authoritative Phase-5 amendment until the consolidated register is next regenerated.

## OD-V2-24 — Host environment policy

**Status: FROZEN**

Binding decision is recorded in `docs/v2/adr/ADR-013-phase5-host-resilience-policy.md`.

Summary:
- Windows 11 x64 is the first-class V2.0 qualification target.
- one trading-engine instance per profile/machine context;
- active Paper/future Live sessions request sleep/hibernate prevention without permanently rewriting OS power plans;
- sleep/resume uncertainty forces `DEGRADED -> RECOVERY` before new entries;
- watchdog restart is RECOVERY-only and never auto-arms;
- clock health is injectable/versioned and fails closed when missing/invalid/exceeded;
- minimum hardware and exact drift threshold come from measured evidence rather than guessed constants;
- antivirus/security protections are not required to be disabled.

## OD-V2-19 — Alert channels and independence

**Status: FROZEN**

Binding decision is recorded in `docs/v2/adr/ADR-014-phase5-alert-channel-independence.md`.

Summary:
- critical alerts use two required independent paths: local on-screen/Windows-visible + Telegram;
- email is an optional third channel;
- adapters share a versioned alert contract but delivery attempts are independent;
- one channel failure cannot suppress the other;
- payloads are minimal/redacted and contain no credentials, tokens, raw account identifiers, or unrestricted trade logs;
- notifier outage cannot weaken paper safety/recovery logic;
- remote dead-PC heartbeat is deferred until OD-V2-22 telemetry/privacy governance is frozen.

## Phase 5 entry consequence

The Phase-5-specific Owner Decision blockers are now frozen. This authorizes architectural design/spec work for **Paper V2, Reconciliation & Recovery**. It does **not** authorize:
- Live broker mutation;
- Live arming;
- merge of PR #6 or PR #7;
- bypass of G5 evidence requirements;
- automatic strategy promotion.

Implementation still requires the Phase-5 design/spec and implementation-plan review gates before production code is changed.