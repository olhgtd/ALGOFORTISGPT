# ADR-013 — Phase 5 Host Resilience Policy

**Status:** FROZEN  
**Date:** 2026-09-25  
**Owner decision:** OD-V2-24  
**Phase:** 5 — Paper V2, Reconciliation & Recovery

## Context

AlgoFortis V2 is local-first and runs trading engines on a Windows PC. Phase 5 must prove paper-session recovery under host failures without weakening the standing safety contract. Live remains `READ_ONLY/DISARMED`; this ADR does not authorize real-broker mutation or live arming.

## Decision

OD-V2-24 is frozen with the following V2.0 policy:

1. **Supported host baseline:** Windows 11 x64 is the first-class V2.0 desktop target. Other Windows editions are not qualification targets unless separately added to the compatibility matrix and CI evidence.
2. **Single engine instance:** one AlgoFortis trading-engine instance per local profile/machine context. A second instance must fail closed before session ownership is acquired.
3. **Sleep/hibernate:** while a Paper or future Live trading session is active, AlgoFortis must request prevention of automatic sleep/hibernate. The implementation must not silently modify permanent OS power-plan settings.
4. **Resume handling:** any detected sleep/hibernate/resume discontinuity during a trading session invalidates normal-running assumptions and forces a `DEGRADED -> RECOVERY` path before new entries may resume. Recovery must reconcile persisted/owned state first.
5. **Watchdog:** a supervisor may restart a crashed engine only into `RECOVERY`. It must never restart directly into an armed/active state and must never create an auto-arm path.
6. **Clock health:** session preflight and recovery must use an injectable/versioned clock-health policy. The allowed drift threshold is configuration/evidence driven; no production numeric limit is invented in Phase 5 code. Missing, invalid, or exceeded clock-health policy fails closed for entry eligibility and produces audit/alert evidence.
7. **Hardware support profile:** Phase 5 will record a measured Windows performance/resource baseline and publish the minimum supported hardware profile from evidence. No unsupported numeric hardware minimum is guessed in this ADR. Resource pressure must be observable and must not silently bypass safety.
8. **Antivirus/security software:** AlgoFortis must not require antivirus or Windows security protections to be disabled. Diagnostics may identify file/network interference and document narrowly scoped allow-list guidance only when evidence shows it is necessary.
9. **Recovery precedence:** reconciliation/recovery safety takes precedence over retries, new entries, and normal session continuation after host uncertainty.
10. **Audit:** instance-lock acquisition/failure, sleep/resume detection, watchdog restart, clock-health failure, recovery entry and recovery completion must be auditable events.

## Consequences

- Phase 5 host-resilience work implements AF2-HOST-001 through AF2-HOST-004 within the paper/recovery boundary.
- Existing `LiveStateMachine.restore_after_restart` / `restore_after_crash` semantics remain the safety reference: restart/crash returns to `RECOVERY` with arm disabled.
- Host checks must be testable through injected/fake providers; tests must not depend on changing the CI runner's real sleep, clock, or power settings.
- No Phase 5 component may use host recovery as a route to enable Live.

## Verification requirements

Phase 5 evidence must include deterministic tests for:

- second-instance rejection;
- sleep/resume -> recovery transition;
- crash/watchdog restart -> recovery only;
- unhealthy/missing clock policy -> fail closed;
- recovery-before-entry sequencing;
- audit failure on a trading-critical state change -> mutation blocked;
- Windows CI qualification without changing permanent runner power settings.

## Non-decisions

- Exact production clock-drift seconds are deferred until measured evidence supports a versioned policy.
- Exact minimum CPU/RAM/disk values are deferred until Phase 5 performance/resource baselines exist.
- This ADR does not decide OD-V2-19 alert-channel independence.
- This ADR does not change Live state, broker access, or promotion eligibility.
