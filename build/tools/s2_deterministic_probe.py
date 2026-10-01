"""Emit deterministic, machine-comparable GP-S2 evidence."""
from __future__ import annotations

from dashboard.backend.account_v2.evidence import (
    build_gp_s2_evidence,
    evidence_fingerprint,
    render_gp_s2_evidence,
)


def main() -> None:
    evidence = build_gp_s2_evidence()
    rendered = render_gp_s2_evidence(evidence).decode("utf-8")
    print(rendered, end="")
    print(f"GP_S2_FINGERPRINT={evidence_fingerprint(evidence)}")


if __name__ == "__main__":
    main()
