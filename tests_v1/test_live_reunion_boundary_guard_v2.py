from build.tools.check_live_reunion_boundary import check_source_text


def test_paper_coordinator_local_cancel_is_not_broker_mutation() -> None:
    source = """
class PaperExecutionCoordinator:
    def cancel_order(self, order_id: str) -> None:
        return None

    def replace_order(self, order_id: str) -> None:
        self.cancel_order(order_id)
"""

    assert check_source_text("engine/paper/coordinator.py", source) == []


def test_paper_coordinator_nested_broker_cancel_remains_forbidden() -> None:
    source = """
class PaperExecutionCoordinator:
    def cancel_real_order(self, order_id: str) -> None:
        self.broker.cancel_order(order_id)
"""

    failures = check_source_text("engine/paper/coordinator.py", source)

    assert any("direct broker mutation call 'cancel_order' is forbidden" in failure for failure in failures)


def test_other_noncanonical_self_cancel_remains_forbidden() -> None:
    source = """
class StrategyRuntime:
    def cancel(self, order_id: str) -> None:
        self.cancel_order(order_id)
"""

    failures = check_source_text("engine/strategy/runtime.py", source)

    assert any("direct broker mutation call 'cancel_order' is forbidden" in failure for failure in failures)
