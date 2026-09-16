"""Tests for AlgoFortis Area 15 — Security Remediations (Fix 1, Fix 2, Fix 3).

Verifies:
1. Information leakage: all audited endpoints return client-safe constant error codes
   and never leak raw str(exc), exception reprs, SQLite paths, or internal tracebacks.
2. HTTP Rate Limiting: auth endpoints enforce 5-failure progressive cooldown with
   per-account isolation; expensive endpoints enforce per-user request throttling (HTTP 429).
3. User isolation: User A's lockout or throttling never affects User B.
"""
import tempfile
import sqlite3
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from dashboard.backend.security_store import SQLiteSecurityStore
from dashboard.backend.governance_store import SQLiteGovernanceStore
from dashboard.backend.core_audit import MandatoryCoreSecurityAudit
from dashboard.backend.domain import (
    UserIdentity, Role, Lifecycle, AccessRoute,
    AccountAccessStatus, ActivationStatus, ServiceEntitlementStatus,
)
from dashboard.backend.security import WebAuthnCeremonyService, WebAuthnRelyingParty
from dashboard.backend.auth_policy import AuthPolicyManager, RateLimitTracker
from dashboard.backend.api import create_app


class InMemoryAuditAuthority:
    def __init__(self):
        self.events = []
        self.should_fail = False

    def append_audit_events(self, events):
        if self.should_fail:
            raise RuntimeError("Simulated Core Audit write failure (authoritative append rejected on C:\\Secret\\Path)")
        self.events.extend(events)
        return tuple(events)


class DummyHistoricalDataService:
    def __init__(self):
        self.should_fail_import = False
        self.should_fail_sync = False
        self.should_fail_repair = False

    def import_dataframe(self, frame, **kwargs):
        if self.should_fail_import:
            raise RuntimeError("Database corruption at C:\\Users\\Secret\\Data\\db.bin")
        class Item:
            instrument = "NIFTY"
            timeframe = "1m"
            row_count = len(frame)
            file_sha256 = "dummy_sha256"
        return Item()

    def sync_dataset(self, **kwargs):
        if self.should_fail_sync:
            raise RuntimeError("Upstream provider failure at https://secret-broker.internal/v1")
        class Job:
            job_id = "job-123"
            status = "COMPLETED"
        return Job()

    def repair_gaps(self, **kwargs):
        if self.should_fail_repair:
            raise RuntimeError("Gap repair failed with raw internal error on worker-04")
        class Report:
            success = True
            repaired_gaps = 0
        return Report()

    def list_inventory(self):
        return []

    def check_inventory(self, inst, tf):
        return None

    def calculate_missing_intervals(self, **kwargs):
        return []


def build_test_context():
    temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    tpath = Path(temp_dir.name)
    sec_db = tpath / "security.sqlite3"
    gov_db = tpath / "governance.sqlite3"

    sec = SQLiteSecurityStore(sec_db, profile="test", seed_governance=False)
    gov = SQLiteGovernanceStore(gov_db)
    audit_auth = InMemoryAuditAuthority()
    core_audit = MandatoryCoreSecurityAudit(audit_store=audit_auth, security_store=sec)
    hist_service = DummyHistoricalDataService()
    auth_policy = AuthPolicyManager()
    ceremonies = WebAuthnCeremonyService(
        store=sec,
        normal_rp=WebAuthnRelyingParty("localhost", "http://localhost:8000", development_only=True),
    )

    owner_id = uuid4()
    owner = UserIdentity(
        user_id=owner_id,
        role=Role.OWNER,
        lifecycle=Lifecycle.ACTIVE,
        display_name="Owner",
        account_status=AccountAccessStatus.ACTIVE,
        activation_status=ActivationStatus.REDEEMED,
        service_status=ServiceEntitlementStatus.ACTIVE,
    )
    sec.ensure_user(
        user_id=owner_id,
        role="OWNER",
        lifecycle="ACTIVE",
        display_name="Owner",
        account_status="ACTIVE",
        activation_status="REDEEMED",
        service_status="ACTIVE",
    )

    user_a_id = uuid4()
    user_a_identity = UserIdentity(
        user_id=user_a_id,
        role=Role.USER,
        lifecycle=Lifecycle.ACTIVE,
        display_name="User A",
        account_status=AccountAccessStatus.ACTIVE,
        activation_status=ActivationStatus.REDEEMED,
        service_status=ServiceEntitlementStatus.ACTIVE,
    )
    sec.ensure_user(
        user_id=user_a_id,
        role="USER",
        lifecycle="ACTIVE",
        display_name="User A",
        account_status="ACTIVE",
        activation_status="REDEEMED",
        service_status="ACTIVE",
    )
    user_b_id = uuid4()
    user_b_identity = UserIdentity(
        user_id=user_b_id,
        role=Role.USER,
        lifecycle=Lifecycle.ACTIVE,
        display_name="User B",
        account_status=AccountAccessStatus.ACTIVE,
        activation_status=ActivationStatus.REDEEMED,
        service_status=ServiceEntitlementStatus.ACTIVE,
    )
    sec.ensure_user(
        user_id=user_b_id,
        role="USER",
        lifecycle="ACTIVE",
        display_name="User B",
        account_status="ACTIVE",
        activation_status="REDEEMED",
        service_status="ACTIVE",
    )

    app = create_app(
        owner=owner,
        security_store=sec,
        governance_store=gov,
        core_security_audit=core_audit,
        historical_data_service=hist_service,
        webauthn_ceremonies=ceremonies,
        auth_policy=auth_policy,
        artifact_root=tpath / "artifacts",
    )

    # Pre-issue sessions
    owner_session = app.state.sessions.issue(user=owner, route=AccessRoute.NORMAL, mtls_verified=True, step_up_satisfied=True)
    user_a_session = app.state.sessions.issue(user=user_a_identity, route=AccessRoute.NORMAL, mtls_verified=True, step_up_satisfied=True)
    user_b_session = app.state.sessions.issue(user=user_b_identity, route=AccessRoute.NORMAL, mtls_verified=True, step_up_satisfied=True)

    client = TestClient(app)
    return {
        "temp_dir": temp_dir,
        "sec": sec,
        "gov": gov,
        "audit_auth": audit_auth,
        "hist_service": hist_service,
        "auth_policy": auth_policy,
        "app": app,
        "client": client,
        "owner_headers": {"Authorization": f"Bearer {owner_session.token}"},
        "user_a_headers": {"Authorization": f"Bearer {user_a_session.token}"},
        "user_b_headers": {"Authorization": f"Bearer {user_b_session.token}"},
        "user_a_id": user_a_id,
        "user_b_id": user_b_id,
    }


def test_fix1_reports_query_backtest_runs_leakage_prevented():
    ctx = build_test_context()
    client = ctx["client"]
    headers = ctx["owner_headers"]
    sec = ctx["sec"]

    # Induce an exception in list_backtest_runs with a sensitive internal message
    def faulty_list_runs(*args, **kwargs):
        raise sqlite3.OperationalError("no such table: secret_table_at_C:\\Users\\Internal\\db.sqlite")

    original = sec.list_backtest_runs
    sec.list_backtest_runs = faulty_list_runs
    try:
        res = client.get("/api/v1/owner/reports", headers=headers)
        assert res.status_code == 503
        detail = res.json()["detail"]
        assert detail == "QUERY_BACKTEST_RUNS_FAILED"
        assert "secret_table" not in res.text
        assert "OperationalError" not in res.text
        assert "C:\\Users" not in res.text
    finally:
        sec.list_backtest_runs = original


def test_fix1_reports_query_paper_sessions_leakage_prevented():
    ctx = build_test_context()
    client = ctx["client"]
    headers = ctx["owner_headers"]
    sec = ctx["sec"]

    def faulty_list_sessions(*args, **kwargs):
        raise RuntimeError("Fatal memory mapping failure at D:\\Secret\\Paper\\store.sqlite")

    original = sec.list_paper_sessions
    sec.list_paper_sessions = faulty_list_sessions
    try:
        res = client.get("/api/v1/owner/reports", headers=headers)
        assert res.status_code == 503
        detail = res.json()["detail"]
        assert detail == "QUERY_PAPER_SESSIONS_FAILED"
        assert "Fatal memory" not in res.text
        assert "D:\\Secret" not in res.text
    finally:
        sec.list_paper_sessions = original


def test_fix1_audit_recording_leakage_prevented():
    ctx = build_test_context()
    client = ctx["client"]
    headers = ctx["owner_headers"]
    ctx["audit_auth"].should_fail = True

    payload = {
        "display_name": "Test User",
        "email": "test_audit_leak@example.com",
        "role": "USER",
    }
    res = client.post("/api/v1/owner/access/users", json=payload, headers=headers)
    assert res.status_code == 503
    detail = res.json()["detail"]
    assert detail == "Mandatory security audit recording failed: AUDIT_RECORDING_FAILED"
    assert "C:\\Secret\\Path" not in res.text


def test_fix1_market_data_import_and_sync_leakage_prevented():
    ctx = build_test_context()
    client = ctx["client"]
    headers = ctx["owner_headers"]
    hist = ctx["hist_service"]

    # 1. Import failure
    hist.should_fail_import = True
    payload = {
        "instrument": "NIFTY",
        "timeframe": "1m",
        "rows": [{"timestamp": "2026-01-05T09:15:00Z", "open": 24000, "high": 24010, "low": 23990, "close": 24005, "volume": 100}],
    }
    res = client.post("/api/v1/market/data/import", json=payload, headers=headers)
    assert res.status_code == 422
    assert res.json()["detail"] == "MARKET_DATA_IMPORT_FAILED"
    assert "C:\\Users\\Secret" not in res.text

    # 2. Sync failure
    hist.should_fail_sync = True
    sync_payload = {
        "instrument": "NIFTY",
        "timeframe": "1m",
        "start_date": "2026-01-05",
        "end_date": "2026-01-06",
    }
    res_sync = client.post("/api/v1/owner/historical/sync/manual", json=sync_payload, headers=headers)
    assert res_sync.status_code == 422
    assert res_sync.json()["detail"] == "HISTORICAL_SYNC_FAILED"
    assert "secret-broker.internal" not in res_sync.text

    # 3. Gap repair failure
    hist.should_fail_repair = True
    repair_payload = {
        "instrument": "NIFTY",
        "timeframe": "1m",
    }
    res_repair = client.post("/api/v1/owner/historical/gaps/repair", json=repair_payload, headers=headers)
    assert res_repair.status_code == 422
    assert res_repair.json()["detail"] == "GAP_REPAIR_FAILED"
    assert "worker-04" not in res_repair.text


def test_fix2_auth_activation_repeated_abuse_and_cooldown():
    ctx = build_test_context()
    client = ctx["client"]

    # First 2 attempts return 403
    for i in range(2):
        res = client.post(
            "/api/v1/auth/webauthn/activation/redeem",
            json={"identifier": "abuser@example.com", "activation_code": f"INVALID-{i}"},
        )
        assert res.status_code == 403

    # 3rd attempt reaches threshold (3) and triggers lockout (429)
    res_3 = client.post(
        "/api/v1/auth/webauthn/activation/redeem",
        json={"identifier": "abuser@example.com", "activation_code": "INVALID-2"},
    )
    assert res_3.status_code == 429
    assert "RATE_LIMIT_COOLDOWN" in res_3.json()["detail"]

    # Subsequent attempts are blocked during active cooldown
    res_blocked = client.post(
        "/api/v1/auth/webauthn/activation/redeem",
        json={"identifier": "abuser@example.com", "activation_code": "INVALID-3"},
    )
    assert res_blocked.status_code == 429
    assert "RATE_LIMIT_COOLDOWN" in res_blocked.json()["detail"]
    assert "Retry-After" in res_blocked.headers
    retry_after = int(res_blocked.headers["Retry-After"])
    assert 0 < retry_after <= 900


def test_fix2_per_user_isolation_on_auth():
    ctx = build_test_context()
    client = ctx["client"]

    # Lock out User A identifier
    for i in range(3):
        client.post(
            "/api/v1/auth/webauthn/activation/redeem",
            json={"identifier": "victim_target@example.com", "activation_code": f"BAD-{i}"},
        )
    res_a = client.post(
        "/api/v1/auth/webauthn/activation/redeem",
        json={"identifier": "victim_target@example.com", "activation_code": "BAD-X"},
    )
    assert res_a.status_code == 429

    # User B identifier must NOT be locked out
    res_b = client.post(
        "/api/v1/auth/webauthn/activation/redeem",
        json={"identifier": "innocent_user@example.com", "activation_code": "WRONG_ONCE"},
    )
    assert res_b.status_code == 403  # Rejected on credentials, NOT throttled with 429


def test_fix2_expensive_route_throttling_and_user_isolation():
    ctx = build_test_context()
    client = ctx["client"]
    headers_a = ctx["user_a_headers"]
    headers_b = ctx["user_b_headers"]

    valid_source = "class MyStrategy:\n    pass\n"
    # Exhaust expensive limit for User A (threshold = 30)
    for i in range(30):
        res = client.post("/api/v1/strategies", json={"source": valid_source}, headers=headers_a)
        assert res.status_code in {200, 422, 429}

    # 31st call must trigger 429 RATE_LIMIT_EXCEEDED
    res_throttled = client.post("/api/v1/strategies", json={"source": valid_source}, headers=headers_a)
    assert res_throttled.status_code == 429
    assert "RATE_LIMIT_EXCEEDED" in res_throttled.json()["detail"]
    assert "Retry-After" in res_throttled.headers

    # User B must NOT be throttled
    res_b = client.post("/api/v1/strategies", json={"source": valid_source}, headers=headers_b)
    assert res_b.status_code != 429
