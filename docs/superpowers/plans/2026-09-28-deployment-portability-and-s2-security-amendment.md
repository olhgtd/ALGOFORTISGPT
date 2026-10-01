# AlgoFortis V2 — Deployment Portability + S2 Password-Fallback Implementation Plan Amendment

**Date:** 2026-09-28  
**Status:** APPROVED OWNER FOLLOW-UP — IMPLEMENTATION PLAN AMENDMENT  
**Scope of this commit:** documentation / implementation planning only  
**Runtime state:** unchanged; Live remains `READ_ONLY / DISARMED`  
**V2.0 deployment profile:** `LOCAL_PC` only

## 1. Authority and scope

This plan amendment implements the three owner-approved follow-ups to the frozen deployment-portability decision without changing the freeze itself.

It is additive to the existing V2 implementation plans and specifically amends the S2 planning position where `docs/superpowers/plans/2026-09-26-s2-account-device-session-implementation.md` says the wrapper "never adds a password fallback". That sentence is superseded only to the extent necessary to implement the approved authentication decision below. All other S2 requirements remain in force unless explicitly contradicted by a later frozen owner decision.

This plan does **not** authorize remote hosting in V2.0, does **not** expose the engine API to the public Internet, does **not** enable mobile/push, and does **not** arm Live.

## 2. Non-negotiable safety invariants

- OD-V2-02 remains local-first for V2.0.
- OD-V2-27 means deployment portability, not current remote deployment approval.
- `LOCAL_PC` is the only active V2.0 profile; `REMOTE_HOST` is a later deployment profile.
- RiskGateV2 remains the sole executable-order authority.
- Fail-closed behavior is preserved.
- Options remain BUY-only.
- Restart/reconnect/update/host migration never auto-arm and never auto-resume a safety halt.
- Host migration enters `RECOVERY`, reconciles broker/runtime state, reaches an explicit ready-for-resume condition, and then requires manual resume.
- Local and future remote engines must never be simultaneously eligible for the same broker account.
- Risk-reducing actions such as Pause / Halt / Exit must not depend on authentication step-up that could block them during an outage or incident.

---

# Workstream A — Enforce deployment portability in code structure

## Task A1 — Add a portability static guard

**Files to create during implementation:**

- `scripts/check_deployment_portability.py`
- `dashboard/tests/test_deployment_portability_guard.py`

**Purpose:** turn the OD-V2-27 portability rule into an executable architecture check so host-specific dependencies cannot silently creep into domain/core modules.

### Guard behavior

The checker must inspect the configured domain/core module roots and fail non-zero with actionable `file:line` diagnostics when prohibited host-specific usage appears directly in those modules.

At minimum, detect direct use of:

- `os.environ` / direct environment-variable reads from domain code;
- hard-coded absolute host paths, including Windows drive paths and UNC paths;
- DPAPI / Windows credential APIs from domain code;
- direct Windows-only API imports/usages such as `winreg`, `win32crypt`, `win32api`, or equivalent Windows API bindings;
- `ctypes.windll` or equivalent direct Windows API entry points in domain code.

The implementation may extend this list when equivalent host-coupled mechanisms are discovered, but it must not invent broad bans that prevent legitimate standard-library domain logic.

### Allowed boundary

Host-specific code is allowed only behind approved ports/adapters or in composition/bootstrap code. The checker must use an explicit allowlist/scope rather than blanket-scanning docs, tests, generated assets, vendored dependencies, migrations, or adapter implementations and producing false positives.

### RED tests first

`dashboard/tests/test_deployment_portability_guard.py` must prove at least:

1. a domain fixture using `os.environ` fails;
2. a domain fixture with a hard-coded Windows/UNC path fails;
3. a domain fixture importing/using DPAPI or a Windows API fails;
4. the equivalent dependency inside an approved host adapter passes;
5. ordinary portable domain code passes;
6. the checker returns a stable non-zero exit code and useful path/line output for violations.

### Verification commands

```powershell
pytest -q dashboard/tests/test_deployment_portability_guard.py
python scripts/check_deployment_portability.py
```

When implementation begins, wire the checker into the repository's existing local architecture/golden verification path and CI verification path so a future violating commit cannot qualify silently.

The checker itself is an architecture guard; it must not change runtime trading behavior.

---

## Task A2 — Make host dependencies explicit ports/adapters

During implementation, host-dependent capabilities must remain behind explicit interfaces/adapters. At minimum the design must cover:

- paths / filesystem locations;
- secret storage;
- durable storage;
- clock/time source where host behavior matters;
- host lifecycle / restart / recovery signals;
- alert delivery/local notification integration.

The exact interface names should follow repository conventions discovered during implementation; do not introduce parallel abstractions merely to match names in this document.

`LOCAL_PC` provides the current Windows implementation. `REMOTE_HOST` adapters are **not** implemented merely because the seam exists.

Domain/core modules must not encode Windows, DPAPI, fixed-drive, local-user-profile, power/sleep, or alert-provider assumptions directly.

---

## Task A3 — Headless/versioned API seam without public exposure

The engine must be capable of headless operation and expose a versioned authenticated API boundary from day one of the portability implementation.

For V2.0:

- bind remains localhost/local-machine by default;
- Internet exposure is not enabled;
- remote-host networking, public TLS termination, mobile relay, and cloud ingress are not V2.0 deliverables;
- authentication/authorization semantics must be present even on localhost so a later deployment profile does not require redesigning the engine contract.

---

## Task A4 — Backup/restore and profile cutover qualification

Host/profile migration uses the frozen `AlgoFortisBackup/v1` backup-and-restore contract.

Required cutover sequence:

1. make the old engine ineligible for new entries;
2. stop/settle the old profile according to the approved operational procedure;
3. create/verify the backup;
4. restore on the target host/profile;
5. start the target in `RECOVERY`;
6. reconcile broker positions/orders/runtime state;
7. reach the explicit ready-for-resume state;
8. require manual resume/arming as applicable.

If ownership/exclusivity is ambiguous at any point, enforce the OD-V2-05 response: halt new entries, audit/alert, and reconcile. Never perform automatic takeover or automatic arm.

Any future target profile must rerun the applicable golden suite and failure-injection qualification on that target before it can become eligible.

---

# Workstream B — Future cloud go-live trigger set

These items are **not V2.0 gates**. They become mandatory only when a future owner decision actually proposes cloud/remote go-live.

Existing cloud go-live triggers remain:

- mobile client / push-notification architecture;
- hosted trade/position data privacy re-review under OD-V2-25, including updated notice/consent and dated qualified legal review;
- dated OD-V2-09 verification for then-current broker/exchange/regulatory/static-IP requirements;
- remote-host secret-custody/KMS choice;
- external/independent security testing before an Internet-facing engine API goes live.

## Added trigger — target OS + host-adapter parity

Before a future `REMOTE_HOST` profile can go live, explicitly select and qualify the target operating system. Do not assume it will be Windows or Linux in advance.

If the target OS differs from the currently frozen Windows 11 local host, provide and qualify target-host counterparts for every host-dependent capability used by the engine, including at minimum:

- lifecycle/restart/host-health behavior;
- power/sleep semantics or their remote-host equivalent;
- secret-store implementation / KMS adapter;
- filesystem/path/storage adapter behavior;
- clock/timezone behavior relevant to trading/recovery;
- local/host alert counterpart;
- backup/restore behavior;
- safe update-window behavior.

Create a target-OS/adapter parity matrix for the go-live review. A missing or unqualified counterpart is a go-live blocker, not a reason to leak target-OS assumptions back into domain code.

If the engine API will be Internet-facing, public-network controls/TLS/authentication exposure and the required external security test are qualified at that future gate, not in V2.0 local-only qualification.

---

# Workstream C — S2 password-fallback qualification

## Task C1 — Amend the S2 authentication planning assumption

Passkey/WebAuthn remains preferred. Password fallback is allowed.

A password-authenticated session by itself is lower assurance and must **not** authorize the following sensitive actions without successful step-up to the required stronger assurance:

- Arm Live;
- broker credential/key create/change/replace;
- enroll a new device;
- revoke a device;
- delete the account.

Pause, Halt, Exit, and equivalent risk-reducing actions must remain available without adding a new step-up dependency.

Hashing, breached-password checking, credential-stuffing resistance, rate limiting, progressive lockout/cooldown, and secret-safe logging are implementation requirements. Exact production parameters must come from the approved security policy/configuration and supporting review; this plan must not invent numeric thresholds.

## Task C2 — Add RED qualification tests before implementation

**Files to create/modify during implementation:**

- Create `dashboard/tests/test_s2_password_fallback.py`
- Modify `dashboard/tests/test_s2_critical_action_auth.py`
- Create `dashboard/tests/test_s2_auth_abuse_resistance.py`

Required tests:

1. password fallback can establish only the assurance level permitted by the auth contract;
2. a password-only session attempting **Arm Live** is denied;
3. a password-only session attempting broker credential/key mutation is denied;
4. a password-only session attempting new-device enrollment is denied;
5. a password-only session attempting device revocation is denied;
6. a password-only session attempting account deletion is denied;
7. after approved step-up, the corresponding action can proceed only if every other authorization/safety requirement also passes;
8. Pause/Halt/Exit remains available without requiring that step-up;
9. credential-stuffing/rate-limit behavior is exercised against the configured policy rather than hard-coding an invented threshold in the test plan;
10. lockout/cooldown behavior is exercised against the configured policy;
11. breached-password handling is tested according to the chosen approved breach-check mechanism without leaking the password;
12. passkey/WebAuthn login and existing device/session qualification remain green;
13. logs/errors/audit payloads do not expose raw passwords, broker secrets, recovery secrets, or authentication material.

### Focused verification

```powershell
pytest -q dashboard/tests/test_s2_password_fallback.py
pytest -q dashboard/tests/test_s2_critical_action_auth.py
pytest -q dashboard/tests/test_s2_auth_abuse_resistance.py
```

Then run the full S2 qualification set and existing golden/security suites.

## Task C3 — Amend GP-S2 qualification gates

The existing GP-S2 list is additively amended with these binding gates:

- **GP-S2-PW-01:** password fallback path is qualified while Passkey/WebAuthn remains preferred;
- **GP-S2-PW-02:** explicit test proves **password-only cannot Arm Live**;
- **GP-S2-PW-03:** password-only cannot mutate broker credentials/keys without approved step-up;
- **GP-S2-PW-04:** password-only cannot enroll/revoke a device or delete the account without approved step-up;
- **GP-S2-PW-05:** risk-reducing Pause/Halt/Exit paths do not gain a new step-up dependency;
- **GP-S2-PW-06:** credential-stuffing, rate-limit, and lockout/cooldown behavior is qualified against the approved configurable policy;
- **GP-S2-PW-07:** breached-password handling is qualified against the selected approved mechanism;
- **GP-S2-PW-08:** existing passkey, session, recovery, audit, and critical-action tests remain green.

No GP-S2 item may be declared satisfied solely because a UI button is hidden; server-side authorization/assurance enforcement must be tested.

---

# Execution order for the coding phase

When coding is authorized, execute in this order:

1. RED portability-guard tests.
2. Implement `check_deployment_portability.py` and make focused tests GREEN.
3. Introduce/refine only the minimum host ports/adapters needed to remove violations found by the guard; keep `LOCAL_PC` behavior unchanged.
4. Qualify headless/versioned authenticated localhost API seam without public exposure.
5. RED S2 password-fallback/step-up/abuse-resistance tests.
6. Implement the minimum S2 auth changes required by the approved contract.
7. Add the GP-S2 gates to the qualification runner/checklist.
8. Run focused suites, full S2 suite, portability checker, existing golden/security suites, and applicable Windows qualification.
9. Review diff for accidental Live enabling, remote-host enablement, public API exposure, or unrelated refactors.

## Definition of done for this implementation plan

The future coding change is not complete until all of the following are true:

- portability checker is executable and enforced in qualification/CI;
- domain/core host-coupling violations fail qualification;
- `LOCAL_PC` remains the V2.0 active deployment profile;
- no `REMOTE_HOST` go-live behavior is enabled;
- cloud/mobile/privacy/static-IP/KMS/public-API security items remain future go-live triggers;
- target-OS + host-adapter parity is explicitly part of that future gate;
- password-only cannot Arm Live or perform the listed sensitive mutations without step-up;
- abuse-resistance qualification exists without invented production numbers;
- risk-reducing actions remain available without the new step-up requirement;
- Live remains `READ_ONLY / DISARMED` until its separately frozen eligibility gates are satisfied.
