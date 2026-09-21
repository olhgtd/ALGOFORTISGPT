# AlgoFortis V2 — G0 Evidence Ledger

**Gate:** G0 — Decision Freeze & V1 Freeze Audit  
**Status:** **PASS — evidence complete**  
**Date:** 2026-09-21  
**Primary verified source head:** `b173d2454eeab52ffd61ed4f86afae360d768b39`  
**Primary verification run:** GitHub Actions `35547332775` — SUCCESS

## Required evidence

| G0 requirement | Status | Evidence |
|---|---|---|
| OD-V2-01 frozen | **PASS** | `ALGOFORTIS_V2_OWNER_DECISIONS.md` — revised Phase 0–10 plan canonical; ADR-001 |
| OD-V2-02 frozen | **PASS** | local-first V2.0; cloud account/device/entitlement authority only; ADR-001 |
| OD-V2-03 frozen | **PASS** | V2.0 = T0 + T1; T2 seam-only unless explicitly excepted; ADR-001 |
| OD-V2-12 frozen | **PASS** | Decimal/fixed-point money/price/qty/risk; analytics floats require declared tolerance; ADR-008 |
| V1 current-head baseline captured | **PASS** | `docs/v2/phase0/CURRENT_HEAD_BASELINE.md` |
| V1 whole-repository audit report | **PASS** | `docs/v2/phase0/V1_AUDIT_REPORT.md` |
| V1 contract freeze list | **PASS** | `docs/v2/phase0/V1_CONTRACT_FREEZE.md` |
| V1→V2 gap register | **PASS** | `docs/v2/phase0/V1_GAP_REGISTER.md` |
| Fresh current-head full regression | **PASS** | exact head `b173d245…`; Windows 2025: 209/209 PASS; Windows 2022: 209/209 PASS |
| Existing architectural certification | **PASS** | both clean environments: 13/13 PASS, `REGRESSION VERIFICATION: ALL PASS` |
| Zero open P0/P1 | **PASS** | source audit + current-head verification found 0 open P0 and 0 open P1; non-blocking maintenance warnings only |
| Golden regression definition | **PASS** | `docs/v2/phase0/GOLDEN_REGRESSION_BASELINE.md` |
| Two-clean-environment reproducibility | **PASS** | Windows Server 2025 + Windows Server 2022, exact Python 3.13.14, exact matching deterministic fingerprints |
| Data provenance audit | **PASS FOR G0** | `DATA_PROVENANCE_AUDIT.md`; V1 hash/inventory foundations frozen; full V2 immutable dataset catalog/licensing remains recorded Phase 3 gap G-006 |
| Phase 0 production-code boundary | **PASS** | comparison to Phase 0 base shows no production engine/business-logic source modified by Phase 0 |
| Live safety posture preserved | **PASS** | current live-readiness boundary remains READ_ONLY/SHADOW; no Phase 0 live mutation enablement or arming change |

## Fresh verification evidence

### Environment A

- Windows Server 2025 Datacenter, build 26100.
- Python 3.13.14.
- Exact tested source head: `b173d2454eeab52ffd61ed4f86afae360d768b39`.
- `python -m pytest tests_v1 -q` → **209 passed**, 1 non-failing deprecation warning.
- `python build/tools/run_regression_certification.py` → **13 tests PASS**, `ALL PASS`.

### Environment B

- Windows Server 2022 Datacenter, build 20348.
- Python 3.13.14.
- Exact tested source head: `b173d2454eeab52ffd61ed4f86afae360d768b39`.
- `python -m pytest tests_v1 -q` → **209 passed**, 1 non-failing deprecation warning.
- `python build/tools/run_regression_certification.py` → **13 tests PASS**, `ALL PASS`.

### Deterministic exact-match evidence

- Market-data fingerprint on both environments: `7620420d3bbe9c3dc805947f86d31e64ec6214f43441edc2844ded1f112e0c35`.
- Runtime-config fingerprint on both environments: `6e9168409c73254f8d38ff92025929ed6ebfa104d5150696fdc75ac03efef616`.

Result: **exact cross-environment match** for the captured deterministic components.

## Data coverage qualification

The private source repository does not contain the user's production historical-data corpus. Therefore G0 does **not** claim unobservable multi-year NIFTY/BANKNIFTY coverage. It verifies the V1 integrity/provenance foundations that are present in source and explicitly records the missing universal V2 dataset version/provenance/licence catalog as Phase 3 gap G-006.

This qualification does not block G0 because G0 freezes the starting baseline; G3 remains responsible for proving every V2 dataset version/checksum/provenance/quality/licence requirement before Data V2 passes.

## Non-blocking maintenance findings

- Starlette/AnyIO TestClient deprecation warning during tests — **P2 maintenance**, no failed tests.
- GitHub Actions upstream Node runtime deprecation notices for checkout/setup actions — **CI maintenance**, no failed verification.

Neither finding weakens risk, audit, order isolation, authentication or live-readiness safety.

## G0 ruling

**G0 PASS.** AlgoFortis V1 is accepted as the frozen baseline from which V2 may proceed to Phase 1 Engineering Foundation.

The following remain mandatory:

- `READ_ONLY=true` and `DISARMED=true` remain preserved for live execution during the non-live V2 build/qualification path.
- No real-money live mutation is authorized by G0.
- Known V2 gaps are implemented only in their named phases with tests/evidence; they are not silently folded into V1 contracts.
- Any future P0/P1 finding immediately reopens the relevant gate.

## Trace

- Main Phase 0 base/V2 document commit: `96223c0757004e29b89fe5a00a4aa606957403d2`.
- Isolated branch: `v2-phase0-baseline-audit`.
- Draft PR: #2.
- Successful primary verification run: `35547332775`.
