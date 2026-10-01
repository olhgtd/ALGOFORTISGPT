from datetime import datetime, timezone
from decimal import Decimal

_NOW = datetime(2026, 9, 27, 1, 30, tzinfo=timezone.utc)


class _Audit:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[tuple[str, dict[str, object], bool | None]] = []
        self.observe = None

    def write(self, event_type: str, payload: dict[str, object]) -> None:
        state = self.observe() if self.observe is not None else None
        self.events.append((event_type, payload, state))
        if self.fail:
            raise OSError("audit unavailable")


def _breaker(audit: _Audit):
    from engine.portfolio.v2.circuit_breaker import (
        PortfolioCircuitBreaker,
        PortfolioCircuitBreakerPolicy,
    )

    policy = PortfolioCircuitBreakerPolicy(
        "cb", "v1", Decimal("100"), Decimal("50")
    )
    return PortfolioCircuitBreaker(policy, audit_sink=audit)


def _metrics(*, pnl: str = "0", drawdown: str = "0"):
    from engine.portfolio.v2.circuit_breaker import PortfolioRiskMetrics

    return PortfolioRiskMetrics(Decimal(pnl), Decimal(drawdown), _NOW)


def _authority(allowed: bool = True):
    from engine.portfolio.v2.circuit_breaker import PortfolioResetAuthority

    return PortfolioResetAuthority(allowed, "manual-owner")


def test_daily_loss_or_drawdown_breach_latches_entries_off() -> None:
    audit = _Audit()
    breaker = _breaker(audit)
    audit.observe = lambda: breaker.entries_allowed
    decision = breaker.observe(_metrics(pnl="-100"))
    assert decision.entries_allowed is False
    assert decision.latched is True
    assert decision.reason == "DAILY_LOSS_LIMIT_BREACHED"
    assert audit.events[0][2] is True

    audit2 = _Audit()
    breaker2 = _breaker(audit2)
    decision2 = breaker2.observe(_metrics(drawdown="50"))
    assert decision2.entries_allowed is False
    assert decision2.reason == "DRAWDOWN_LIMIT_BREACHED"


def test_audit_failure_blocks_transition_and_fails_closed() -> None:
    audit = _Audit(fail=True)
    breaker = _breaker(audit)
    decision = breaker.observe(_metrics(pnl="-150"))
    assert decision.latched is False
    assert decision.entries_allowed is False
    assert decision.reason == "AUDIT_WRITE_FAILED"
    assert breaker.entries_allowed is False


def test_healthy_metrics_do_not_auto_reset_latch() -> None:
    audit = _Audit()
    breaker = _breaker(audit)
    breaker.observe(_metrics(pnl="-150"))
    decision = breaker.observe(_metrics())
    assert decision.latched is True
    assert decision.entries_allowed is False
    assert decision.reason == "CIRCUIT_LATCHED"


def test_manual_reset_rejects_without_authority_or_while_metrics_breach() -> None:
    audit = _Audit()
    breaker = _breaker(audit)
    breaker.observe(_metrics(pnl="-150"))
    assert breaker.manual_reset(_authority(False), _metrics()).reason == "RESET_AUTHORITY_DENIED"
    assert breaker.entries_allowed is False
    assert breaker.manual_reset(_authority(True), _metrics(pnl="-101")).reason == "RESET_METRICS_NOT_CLEAN"
    assert breaker.entries_allowed is False


def test_successful_manual_reset_audits_before_state_change() -> None:
    audit = _Audit()
    breaker = _breaker(audit)
    breaker.observe(_metrics(pnl="-150"))
    audit.observe = lambda: breaker.entries_allowed
    decision = breaker.manual_reset(_authority(True), _metrics())
    assert decision.entries_allowed is True
    assert decision.latched is False
    assert decision.reason == "MANUAL_RESET_ACCEPTED"
    reset = audit.events[-1]
    assert reset[0] == "PORTFOLIO_CIRCUIT_MANUAL_RESET"
    assert reset[2] is False


def test_reset_audit_failure_keeps_blocked() -> None:
    audit = _Audit()
    breaker = _breaker(audit)
    breaker.observe(_metrics(pnl="-150"))
    audit.fail = True
    decision = breaker.manual_reset(_authority(True), _metrics())
    assert decision.reason == "AUDIT_WRITE_FAILED"
    assert breaker.entries_allowed is False
