from __future__ import annotations

from pathlib import Path

from build.tools.check_owner_admin_boundary import check_repository, check_source_text


def test_owner_guard_rejects_sample_authority_in_canonical_owner_file() -> None:
    failures = check_source_text(
        "dashboard/owner-dashboard/authoritative/AdminHome.tsx",
        'import { OWNER_USERS } from "../../sampleData";\nexport const x = OWNER_USERS;\n',
    )
    assert any("sample/prototype authority" in item for item in failures)


def test_owner_guard_allows_explicit_preview_fixture_file() -> None:
    failures = check_source_text(
        "dashboard/owner-dashboard/preview/OwnerPreview.tsx",
        'import { OWNER_USERS } from "../../sampleData";\nexport const x = OWNER_USERS;\n',
    )
    assert failures == []


def test_owner_guard_rejects_broker_mutation_and_legacy_approval_tokens() -> None:
    source = """
from engine.broker_adapters.angel_adapter import AngelAdapter

def do_it():
    place_order()
    _mint_approved_order()
"""
    failures = check_source_text("dashboard/backend/owner_admin/mutation_gateway.py", source)
    assert any("forbidden module" in item for item in failures)
    assert any("forbidden authority token 'place_order'" in item for item in failures)
    assert any("forbidden authority token '_mint_approved_order'" in item for item in failures)


def test_entry_gate_guard_rejects_broker_mutation() -> None:
    failures = check_source_text(
        "dashboard/backend/account_v2/password_router.py",
        "def authenticate():\n    cancel_order()\n",
    )
    assert any("forbidden authority token 'cancel_order'" in item for item in failures)


def test_ai_guard_rejects_laya_owned_routing() -> None:
    source = """
class LayaRouter:
    def select_provider(self):
        return 'provider-a'
"""
    failures = check_source_text("engine/ai/laya.py", source)
    assert any("Laya-owned routing" in item for item in failures)


def test_ai_guard_rejects_broker_order_mutation() -> None:
    failures = check_source_text(
        "engine/ai/orchestrator.py",
        "def run():\n    cancel_order()\n",
    )
    assert any("forbidden authority token 'cancel_order'" in item for item in failures)


def test_repository_boundary_guard_passes_current_canonical_tree() -> None:
    failures = check_repository(Path("."))
    assert failures == []
