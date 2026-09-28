# Manual V1 → Current AlgoFortis Adoption Matrix

Legend:

- **ADOPT** — capability/behavior should be carried forward substantially.
- **ADAPT** — valuable implementation/behavior, but must pass through current V2 authority/contracts.
- **TEST-ONLY** — retain primarily as regression/evidence cases rather than runtime implementation.
- **REFERENCE** — useful design/history, not direct production source.
- **IGNORE** — generated, duplicated, obsolete, unsafe or authority-conflicting material.

## Product / UX

| V1 capability | Decision | Current use |
|---|---|---|
| Secure opening / entry UX | ADOPT | premium desktop entry surface; current auth authority underneath |
| Normal User Dashboard | ADOPT | retain mature workflows; all truth from V2 read models/services |
| Owner Dashboard | ADOPT | access, governance, operations, security/system surfaces |
| Market chart/workspace | ADOPT | UI/interaction only; V2 authoritative market data |
| Options workspace | ADOPT | preserve workflow; no SAMPLE/fake option truth |
| Strategy add/upload/paste | ADOPT | connect to current Strategy SDK/registry |
| Strategy governance UI | ADOPT | current governance/promotion evidence authority |
| Backtest UI/workflow | ADOPT | V2 deterministic Backtest authority |
| WFO/OOS UX | ADOPT | V2 research ledger/search-budget/promotion contracts |
| Paper Trading UX | ADOPT | current Paper engine only |
| Live-market Paper | ADOPT | high-value V1 workflow; Paper-only execution authority |
| Orders/Portfolio UI | ADOPT | current canonical projections/read models |
| Live readiness UI | ADOPT | must truthfully reflect READ_ONLY/DISARMED/recovery state |
| Reports/Audit UI | ADAPT | replace simulated export/fake-success with truthful current services |
| Access Registry | ADAPT | current account/device/session contracts |
| Security/System Settings | ADAPT | expose current capabilities, not legacy authority |

## Trading / execution foundations

| V1 capability | Decision | Current use |
|---|---|---|
| Existing deterministic risk/protective knowledge | ADAPT | preserve behavior/tests where compatible; RiskGateV2 remains sole executable-order authority |
| Old V1 RiskGate as runtime authority | IGNORE | must not coexist as parallel approval authority |
| Signal→risk→contract→lots→quantity test chain | TEST-ONLY + ADAPT | preserve invariants around one authoritative quantity conversion |
| Old order lifecycle behavior | ADAPT | use as compatibility cases; V2 lifecycle semantics authoritative |
| Old real broker mutation paths | IGNORE | no authority; Live remains disabled |
| Old duplicate Paper engine | IGNORE | one current Paper authority only |
| Idempotency ledger behavior | ADAPT | preserve replay-protection cases |
| Broker-order worklist/state model | ADAPT | current broker/reconciliation contracts |
| Projection dedup | ADAPT | preserve duplicate-suppression behavior/tests |
| Restart/reattach hydration | ADAPT | V2 RECOVERY/READY_FOR_RESUME/manual-resume semantics |
| Corrupt-state fail-closed | ADOPT | hard invariant |

## Broker / market data

| V1 capability | Decision | Current use |
|---|---|---|
| Upstox catalog/quote normalization | ADAPT | current data gateway/provider adapters |
| Kite instrument/catalog + quote normalization | ADAPT | current data gateway/provider adapters |
| Dhan catalog/quote normalization | ADAPT | current data gateway/provider adapters |
| Angel One catalog/quote normalization | ADAPT | current data gateway/provider adapters |
| token lifecycle / 429 / backoff patterns | ADAPT | current broker/data transport controls |
| reconciliation input patterns | ADAPT | current reconciler |
| non-Upstox WS claims as complete | IGNORE | native streaming for all brokers was not final-V1 certified |
| hard-coded market/lot-size assumptions | IGNORE | authoritative instrument master only |

## Identity / security

| V1 capability | Decision | Current use |
|---|---|---|
| Owner/User RBAC | ADOPT | preserve/port negative tests |
| local scrypt password implementation | REFERENCE + ADAPT | only if current auth spec chooses it; never overwrite account model blindly |
| WebAuthn/FIDO2 origin/RP controls | ADAPT | current interactive-auth boundary |
| refresh-token rotation/reuse detection | ADOPT | current session authority |
| device ceiling / no silent eviction | ADOPT | current device/session authority |
| high-assurance recovery revocation | ADOPT | current recovery contracts |
| Windows DPAPI credential vault principles | ADOPT | local secret-provider abstraction |
| plaintext secret prohibition | ADOPT | permanent invariant |
| secret redaction | ADOPT | logs/audit/support bundle boundary |
| old local-only identity authority as roaming identity | IGNORE | does not satisfy current anywhere-login/central authority |

## Persistence / recovery

| V1 capability | Decision | Current use |
|---|---|---|
| V1 database schemas | REFERENCE | migration/import test source |
| V1 production DB file as current DB | IGNORE | never copy as runtime authority |
| SQLite WAL-safe backup | ADOPT | operational backup foundation |
| data retention/integrity tests | TEST-ONLY + ADAPT | port useful invariants |
| strategy state persistence | ADAPT | current persistence codec/store |
| restart/reconciliation cases | TEST-ONLY + ADAPT | current recovery qualification |

## Backup / installer / platform

| V1 capability | Decision | Current use |
|---|---|---|
| `AlgoFortisBackup/v1` | ADOPT | preserve contract; compatible extension only |
| secret exclusion | ADOPT | permanent backup invariant |
| Zip Slip/path traversal protection | ADOPT | restore boundary |
| data-preserving uninstall | ADOPT | installer/product lifecycle |
| Program Files / LocalAppData split | ADOPT | Windows deployment foundation |
| WebView2 desktop shell | ADOPT | desktop product shell |
| native launcher/runtime lifecycle | ADAPT | current runtime/controller architecture |
| update manifest/SHA validation | ADAPT | current signed update/release track |
| entitlement foundation | REFERENCE + ADAPT | current platform/account track |
| telemetry/privacy redaction | ADAPT | opt-in current policy |
| old unsigned installer binaries | IGNORE | build evidence only; never source authority |

## Tests / evidence

| V1 capability | Decision | Current use |
|---|---|---|
| auth/security/recovery tests | TEST-ONLY + ADAPT | port before implementation salvage |
| backup/restore tests | TEST-ONLY + ADAPT | preserve security regression knowledge |
| installer/reinstall/uninstall tests | TEST-ONLY + ADAPT | current release qualification |
| broker/data tests | TEST-ONLY + ADAPT | provider conformance |
| reconciliation/restart tests | TEST-ONLY + ADAPT | V2 recovery qualification |
| UI workflow tests | TEST-ONLY + ADAPT | current user/owner dashboard qualification |
| final certification manifests/reports | REFERENCE | immutable historical evidence |

## Material that must never be migrated as product source

- `.kilo/worktrees/ember-health` duplicate repository tree;
- `node_modules`;
- build caches;
- `__pycache__`, `.pytest_cache`, IDE caches;
- generated `dist/` and staged build output unless independently rebuilt;
- old installer binaries;
- screenshot/evidence duplicates;
- stale SAMPLE/demo/fake-success data;
- duplicated stores/engines/authorities;
- visible legacy SentinelX branding unless a compatibility identifier explicitly requires it.

## Salvage order

Use authority order, not folder order:

1. regression/security invariants;
2. identity/platform contracts;
3. persistence/recovery patterns;
4. broker/data read-side patterns;
5. product read models;
6. normal User dashboard;
7. Owner dashboard;
8. backup/installer/updater/platform polish;
9. combined qualification.

Do **not** copy `dashboard/` or `engine/` wholesale.
