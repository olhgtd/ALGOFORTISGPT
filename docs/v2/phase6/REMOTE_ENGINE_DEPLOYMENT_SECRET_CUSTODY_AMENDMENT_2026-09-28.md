# AlgoFortis V2 Phase 6 — Deployment Portability & Host-Abstraction Amendment

**Date:** 2026-09-28  
**Status:** OWNER-FROZEN DESIGN AMENDMENT — CORRECTED / NO IMPLEMENTATION AUTHORIZATION  
**Phase:** Phase 6 — Live Execution V2 (still `READ_ONLY / DISARMED`)  
**Authority:** unchanged OD-V2-02 + corrected OD-V2-27 in `docs/v2/REMOTE_SINGLE_TENANT_ENGINE_AUTH_MOBILE_OWNER_DECISION_FREEZE.md`

> **Correction note:** The earlier version of this file incorrectly added a remote-engine deployment/secret-custody implementation path to Phase 6. That is superseded. Phase 6 V2.0 remains local-first.

## 1. Purpose

Phase 6 must keep the local V2.0 broker/execution path portable enough that a future single-tenant remote host can reuse the same engine build with different adapters/configuration rather than a trading-domain rewrite.

This document changes Phase-6 documentation only. It does not add a remote deployment, broker mutation path, workflow, cloud resource, secret store, public endpoint, or production configuration.

## 2. V2.0 execution placement

V2.0 permitted/current execution placement remains:

- `LOCAL_PC` — supported local execution host.

`REMOTE_HOST` is a future deployment profile only. It is not V2.0 scope and is not a Phase-6 exit requirement.

The central Account Authority remains separate and has no trading authority.

## 3. Host-neutral ports/adapters requirement

Phase-6 broker/order/risk application/domain code must consume host-specific services through explicit ports/adapters.

Required boundaries include at least:

- `PathProvider` / filesystem-path abstraction;
- secret-store abstraction;
- execution-state/persistence storage abstraction;
- `Clock` / time-evidence abstraction;
- host lifecycle/health/restart abstraction;
- alert/notifier abstraction;
- bind/network adapter where an API host is involved.

Exact names may differ in the later implementation plan, but the dependency direction is frozen: **domain/application logic must not directly depend on host-specific implementations.**

## 4. Windows/DPAPI assumptions stay at the LOCAL_PC adapter edge

V2.0 may use Windows-specific implementations for `LOCAL_PC`, including approved Windows path resolution, CNG/TPM, DPAPI, service/process integration, and sleep/hibernate handling.

However, trading-domain/application modules must not directly import or assume:

- `%LOCALAPPDATA%` / hard-coded drive paths;
- DPAPI APIs;
- Windows registry/service APIs;
- Windows sleep/hibernate APIs;
- a Windows-only secret format;
- a Windows-only storage path layout;
- Telegram/local-toast delivery implementations.

This preserves the future ability to implement a different `REMOTE_HOST` adapter set without rewriting RiskGate/order/reconciliation logic.

## 5. Headless engine + authenticated API seam

Phase 6 must preserve a headless-capable engine/process boundary with a versioned API contract.

For V2.0:

- API authentication is required from day one;
- API authorization follows S2/session assurance rules;
- default production bind is localhost/local-machine only;
- no internet-facing engine API is required or authorized;
- no API method can bypass `RiskGateV2` or construct `ApprovedOrder` directly;
- password-only session step-up restrictions apply to protected risk-increasing mutations;
- risk-reducing Pause/Halt/Exit remains available under the frozen auth exception;
- the central account service gains no broker mutation endpoint.

## 6. Broker credentials — current local custody

For V2.0, broker credentials remain local under the existing local-first architecture.

This portability amendment does not select or implement:

- cloud secret storage;
- KMS product/provider;
- remote instance IAM/identity;
- remote encrypted-volume design;
- central broker-secret storage.

A future cloud go-live must provide a `REMOTE_HOST` secret-store adapter that preserves the existing no-centralization and secret-redaction invariants. That future design may use KMS-backed custody, but no product/provider is frozen here.

## 7. OD-V2-05 future host cutover rule

The existing OD-V2-05 local safety backstop remains authoritative for V2.0.

Deployment portability freezes an additional future cutover rule:

- the same broker account may never have both `LOCAL_PC` and `REMOTE_HOST` eligible for new entries simultaneously;
- source eligibility must be removed before target eligibility is granted;
- ambiguous/overlapping activity -> halt new entries + auditable alert/evidence + broker reconciliation;
- no automatic takeover;
- no auto-arm on the target host.

A central coordination record may assist but cannot override broker truth or become order authority.

## 8. `AlgoFortisBackup/v1` migration contract

A future host move must use the frozen `AlgoFortisBackup/v1` backup/restore mechanism rather than ad-hoc state copying.

The cutover contract requires:

1. halt/prep the source safely;
2. resolve pending entry state under existing lifecycle/kill-switch rules;
3. capture final reconciliation/audit state;
4. create and verify backup;
5. disable source eligibility;
6. restore target state through target-profile adapters;
7. separately re-establish secrets/device keys that are intentionally non-exportable/not backed up;
8. target starts in `RECOVERY`;
9. broker-truth reconciliation;
10. target-host qualification rerun;
11. explicit manual resume/arming.

No backup/restore success may imply trading readiness by itself.

## 9. Target-host qualification

Before a materially different target host/profile becomes eligible for trading, qualification must re-run at minimum:

- applicable golden suite / deterministic fingerprint checks;
- broker reconciliation cases;
- restart/recovery cases;
- `INV-15` no-auto-arm;
- local/remote exclusivity/cutover case when applicable;
- applicable failure-injection catalogue;
- host adapter secret/audit/redaction tests;
- any required host-specific clock/performance evidence.

Exact production thresholds are evidence-driven and remain unfrozen unless already governed by a separate Owner decision.

## 10. OD-V2-08 unchanged for V2.0

Broker-resident protective-order requirements remain exactly as frozen in ADR-015.

No new remote-host implication is added to current V2.0 Phase-6 scope.

When/if `REMOTE_HOST` moves toward cloud go-live, OD-V2-08 must be re-applied to that deployment and its host/network failure model before production approval.

## 11. OD-V2-09 cloud go-live trigger — not current Phase-6 scope

This portability amendment does not decide or require current Phase-6 work on:

- hosted static-IP requirements;
- hosted-engine broker registration/approval;
- current SEBI/exchange/broker requirements specific to a remote/cloud host;
- provider/region/network topology.

Those become dated OD-V2-09 verification items only when the Owner later activates cloud go-live for `REMOTE_HOST`.

The normal currently frozen OD-V2-09 review obligations for the selected V2.0 broker path remain unchanged.

## 12. Internet-facing API assessment — future cloud trigger

Current V2.0 API is authenticated and localhost/local-machine bound by default.

Therefore an external/independent security test of an **internet-facing engine API** is not a current Phase-6 exit requirement.

Before any future `REMOTE_HOST` engine API is exposed over the internet, the cloud go-live gate must add the appropriate external/independent security assessment against the final network/auth/API architecture.

## 13. Standing constraints

- Live remains `READ_ONLY / DISARMED`.
- V2.0 remains local-first under OD-V2-02.
- `RiskGateV2` remains sole executable-order authority.
- Options remain BUY-only.
- Fail closed on uncertainty.
- Restart/reconnect/update never auto-arms.
- No runtime/code/config/workflow change is authorized by this document.
