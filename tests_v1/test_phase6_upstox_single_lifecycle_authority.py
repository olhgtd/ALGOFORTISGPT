from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "engine" / "data" / "feeds" / "upstox" / "feed.py"


def _tree() -> ast.Module:
    return ast.parse(FEED.read_text(encoding="utf-8"))


def _class() -> ast.ClassDef:
    for node in _tree().body:
        if isinstance(node, ast.ClassDef) and node.name == "UpstoxLiveMarketDataFeed":
            return node
    raise AssertionError("UpstoxLiveMarketDataFeed class missing")


def _method(name: str) -> ast.FunctionDef:
    for node in _class().body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"method {name} missing")


def _called_attributes(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            names.add(child.func.attr)
    return names


def test_legacy_upstox_feed_has_no_second_transport_lifecycle_authority() -> None:
    text = FEED.read_text(encoding="utf-8")
    forbidden = (
        "self._generation_id",
        "self._ws_client",
        "self._runner_thread",
        "def _trigger_reconnect",
        "def _send_raw_ws_message",
        "def _send_subscription_command",
        "uuid.uuid4",
    )
    for token in forbidden:
        assert token not in text

    assert "MarketDataTransportRuntime" in text
    assert "transport_runtime" in text


def test_connect_reconnect_and_close_delegate_to_shared_runtime() -> None:
    assert "connect" in _called_attributes(_method("start_connection"))
    assert "reconnect" in _called_attributes(_method("reconnect"))
    assert "disconnect" in _called_attributes(_method("close"))


def test_subscriptions_are_broker_neutral_runtime_requests() -> None:
    text = FEED.read_text(encoding="utf-8")
    assert "SubscriptionRequest" in text
    assert "runtime.subscribe" in text
    assert "runtime.unsubscribe" in text
    assert '"FULL"' in text


def test_overflow_and_corruption_fail_closed_in_shared_runtime() -> None:
    assert "fail_closed" in _called_attributes(_method("_handle_overflow"))
    assert "fail_closed" in _called_attributes(_method("_handle_corrupt_payload"))


def test_generation_is_read_from_runtime_not_incremented_locally() -> None:
    method = _method("generation_id")
    assert "connection_generation" in FEED.read_text(encoding="utf-8")
    for node in ast.walk(_class()):
        if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Attribute):
            assert node.target.attr != "_generation_id"


def test_testing_sync_helper_never_changes_transport_state() -> None:
    method = _method("complete_synchronization_for_testing")
    calls = _called_attributes(method)
    assert "connect" not in calls
    assert "reconnect" not in calls
    assert "fail_closed" not in calls
    assert "disconnect" not in calls
