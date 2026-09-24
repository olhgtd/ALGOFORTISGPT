# G4 qualification evidence — candidate, not accepted

Phase 4 remains **draft** and Live remains `READ_ONLY` / `DISARMED`.
The built-in `research-only/v1` profile is `NON_PROMOTABLE`.

## Automated checks

- Pre-evidence commit `f9eac698a4517e7ce5df4e3a56195f97dee666ed`:
  [dual-Windows run 110](https://github.com/olhgtd/ALGOFORTISGPT/actions/runs/36003356376)
  passed Windows latest / Windows 2022 (Python 3.13.14), full `tests_v1`, prior
  static/golden/regression certification and the cross-Windows fingerprint compare.
- The CI workflow requires matching ORB and Backtest V2 fingerprints from both
  Windows runners. The next exact-head run must also pass after this document
  and later fixes are committed. The run above does **not** qualify a later head.
- `TEST_ONLY`/synthetic probe data must yield `NON_PROMOTABLE`; a fixture is
  never evidence for a numeric production promotion profile.

## Unresolved acceptance risks

The current research validation uses supplied WFO/OOS scores and stress summaries;
it does not independently execute all WFO windows, Monte Carlo or regime stresses.
The ORB reference emits research signals but is not wired to a policy-resolved
end-to-end options backtest. Options model assumptions and local batch state are
research primitives, not demonstrated production evidence. An Owner-approved
ORB protective policy and evidence-derived numeric promotion profiles are absent.

G4 is **not accepted** until those paths are implemented, reviewed and the
evidence commit itself receives a fresh exact-head dual-Windows green run.
