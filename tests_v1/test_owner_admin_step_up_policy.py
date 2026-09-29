from dashboard.backend.owner_admin.step_up import classify_destructive_route


def test_destructive_owner_routes_are_step_up_classified() -> None:
    cases = {
        ("POST", "/api/v1/owner/access/users/U-1/suspend"): ("ACCOUNT_SUSPEND", "U-1"),
        ("POST", "/api/v1/owner/access/users/U-1/revoke"): ("ACCOUNT_REVOKE", "U-1"),
        ("POST", "/api/v1/owner/access/users/U-1/extend-service"): ("ENTITLEMENT_CHANGE", "U-1"),
        ("POST", "/api/v1/owner/security/sessions/S-1/revoke"): ("SESSION_REVOKE", "S-1"),
        ("POST", "/api/v1/owner/security/devices/C-1/revoke"): ("DEVICE_REVOKE", "C-1"),
        ("POST", "/api/v1/security/credentials/C-1/lifecycle"): ("CREDENTIAL_LIFECYCLE", "C-1"),
        ("POST", "/api/v1/owner/strategies/ST-1/allowance"): ("STRATEGY_GOVERNANCE", "ST-1"),
        ("POST", "/api/v1/owner/connections/CN-1/allowance"): ("CONNECTION_GOVERNANCE", "CN-1"),
        ("POST", "/api/v1/owner/datasets/D-1/approval"): ("DATASET_GOVERNANCE", "D-1"),
        ("POST", "/api/v1/owner/settings/confirm"): ("SETTINGS_APPLY", None),
        ("POST", "/api/v1/owner/admin/ai/providers/P-1/verify"): ("AI_PROVIDER_VERIFY", "P-1"),
        ("POST", "/api/v1/owner/admin/ai/providers/P-1"): ("AI_PROVIDER_CONFIG", "P-1"),
        ("POST", "/api/v1/owner/admin/ai/agents/laya/binding"): ("AI_AGENT_POLICY", "laya"),
        ("POST", "/api/v1/owner/admin/ai/jobs"): ("AI_JOB_START", None),
    }
    for request, expected in cases.items():
        assert classify_destructive_route(*request) == expected


def test_read_only_owner_routes_do_not_require_mutation_grant() -> None:
    assert classify_destructive_route("GET", "/api/v1/owner/admin/authority") is None
    assert classify_destructive_route("GET", "/api/v1/owner/admin/ai") is None
    assert classify_destructive_route("GET", "/api/v1/owner/admin/users/U-1/inspection") is None
