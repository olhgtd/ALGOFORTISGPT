from __future__ import annotations

import re

from dashboard.backend.account_v2.evidence import (
    build_gp_s2_evidence,
    evidence_fingerprint,
    render_gp_s2_evidence,
)


def test_identical_s2_fixtures_produce_byte_identical_evidence() -> None:
    first = build_gp_s2_evidence()
    second = build_gp_s2_evidence()

    assert render_gp_s2_evidence(first) == render_gp_s2_evidence(second)
    assert evidence_fingerprint(first) == evidence_fingerprint(second)
    assert re.fullmatch(r"[0-9a-f]{64}", evidence_fingerprint(first))


def test_gp_s2_required_markers_are_present_and_fail_closed() -> None:
    evidence = build_gp_s2_evidence()
    required = {
        "S2_SCHEMA_VERSION",
        "ACCOUNT_AUTHORITY_FINGERPRINT",
        "DEVICE_REPROOF_FINGERPRINT",
        "SESSION_REPLAY_RESULT",
        "CROSS_USER_ESCAPE_COUNT",
        "OUTAGE_GATE_STATUS",
        "OUTAGE_RUNTIME_MODE",
        "DEVICE_LIMIT",
        "PRODUCTION_DOMAIN",
        "LIVE_STATE",
        "BROKER_MUTATION_CAPABILITY",
    }

    assert required <= set(evidence)
    assert evidence["SESSION_REPLAY_RESULT"] == "FAMILY_REVOKED"
    assert evidence["CROSS_USER_ESCAPE_COUNT"] == "0"
    assert evidence["OUTAGE_GATE_STATUS"] == "AUTHORITY_UNAVAILABLE"
    assert evidence["OUTAGE_RUNTIME_MODE"] == "LOCAL_SAFETY_ONLY"
    assert evidence["DEVICE_LIMIT"] == "3"
    assert evidence["PRODUCTION_DOMAIN"] == "PENDING_EXTERNAL"
    assert evidence["LIVE_STATE"] == "READ_ONLY/DISARMED"
    assert evidence["BROKER_MUTATION_CAPABILITY"] == "ABSENT"
