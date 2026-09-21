# ADR-009 — V2.0 Plugin / Adapter Registry Scope

**Status:** ACCEPTED / FROZEN  
**Date:** 2026-09-21  
**Decision:** OD-V2-14  
**Applies to:** AlgoFortis V2.0 Phase 1 Engineering Foundation

## Context

Phase 1 is blocked by OD-V2-14. The V2 architecture needs replaceable adapters and explicit compatibility/capability metadata, but V2.0 does not require a third-party plugin ecosystem or process sandbox.

The Owner delegated implementation execution and build-order decisions needed to proceed. The documented recommended option is therefore adopted for V2.0.

## Decision

**OD-V2-14 is FROZEN to option (a): internal adapter registry only.**

V2.0 may implement:
- explicit internal adapter manifests;
- stable adapter IDs and version compatibility checks;
- declared capabilities/permissions;
- deterministic registration and lookup;
- fail-closed rejection of duplicate, incompatible or undeclared registrations.

V2.0 must not add:
- arbitrary third-party package discovery/loading;
- unsigned external plugins;
- user-supplied executable plugin code;
- plugin marketplaces;
- sandbox/process-isolation infrastructure solely for plugins.

Signed third-party packages and sandbox/process isolation remain future V2.x decisions behind the same registry contracts.

## Consequences

- Phase 1 may proceed without designing a public plugin ABI.
- The registry stays small enough to verify thoroughly in CI.
- Later external-plugin support must be additive and must not bypass module boundaries, risk, audit, secrets policy or mode isolation.
- This ADR does not authorize any live broker mutation; `READ_ONLY=true` and `DISARMED=true` remain unchanged.

## Trace

Authority: `ALGOFORTIS_V2_OWNER_DECISIONS.md` OD-V2-14 recommendation and Phase 1 blocking matrix. The master decision register must reflect this frozen decision when reconciled on the Phase 1 branch.
