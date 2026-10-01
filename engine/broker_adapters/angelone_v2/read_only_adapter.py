"""Isolated Angel One V2 broker-truth adapter for G6 read-only qualification."""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from engine.broker_adapters.contracts import (
    BrokerAdapterOrderSnapshot,
    BrokerAdapterOrderStatus,
    BrokerAdapterUnavailableError,
    BrokerAuthError,
    BrokerFillFragment,
    BrokerFundsSnapshot,
    BrokerNetworkError,
    BrokerPositionSnapshot,
    BrokerRateLimitError,
)
from engine.broker_adapters.normalization import map_raw_status

from .contracts import AngelOneBrokerProfile, AngelOneReadOnlyHealth, BrokerRuleEvidenceRef
from .rate_policy import BrokerRateClass, BrokerRatePolicy, evaluate_rate
from .session import AngelOneSessionAuthority


_ANGEL_STATUS_TO_CANONICAL = {
    "open": "ACCEPTED",
    "trigger pending": "ACCEPTED",
    "validation pending": "ACCEPTED",
    "partially filled": "PARTIALLY_FILLED",
    "complete": "FILLED",
    "cancelled": "CANCELLED",
    "rejected": "REJECTED",
    "expired": "EXPIRED",
}


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise BrokerAdapterUnavailableError(f"invalid broker {field}") from None
    if not result.is_finite():
        raise BrokerAdapterUnavailableError(f"invalid broker {field}")
    return result


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BrokerAdapterUnavailableError(f"missing broker {field}")
    return value.strip()


class AngelOneReadOnlyAdapter:
    adapter_id = "angelone-v2-read-only"

    def __init__(
        self,
        *,
        profile: AngelOneBrokerProfile,
        session_authority: AngelOneSessionAuthority,
        transport: object,
        rate_policy: BrokerRatePolicy,
        rule_evidence: BrokerRuleEvidenceRef,
        clock: object,
    ) -> None:
        if not isinstance(profile, AngelOneBrokerProfile):
            raise TypeError("profile must be AngelOneBrokerProfile")
        if not isinstance(session_authority, AngelOneSessionAuthority):
            raise TypeError("session_authority must be AngelOneSessionAuthority")
        if transport is None or not callable(getattr(transport, "get", None)):
            raise TypeError("transport must provide get(path)")
        if not isinstance(rate_policy, BrokerRatePolicy):
            raise TypeError("rate_policy must be BrokerRatePolicy")
        if not isinstance(rule_evidence, BrokerRuleEvidenceRef):
            raise TypeError("rule_evidence must be BrokerRuleEvidenceRef")
        if clock is None or not callable(getattr(clock, "now", None)):
            raise TypeError("clock must provide now()")
        self._profile = profile
        self._session = session_authority
        self._transport = transport
        self._rate_policy = rate_policy
        self._rule_evidence = rule_evidence
        self._clock = clock

    def capabilities(self) -> frozenset[str]:
        return frozenset({"profile", "orders", "trades", "positions", "funds", "health"})

    def profile(self) -> AngelOneBrokerProfile:
        return self._profile

    def _now(self) -> datetime:
        value = self._clock.now()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise BrokerAdapterUnavailableError("observation clock unavailable")
        return value

    def _read(self, resource: str, rate_class: BrokerRateClass) -> object:
        health = self._session.health()
        if not health.observation_available:
            raise BrokerAdapterUnavailableError("broker session unavailable for read-only observation")
        decision = evaluate_rate(self._rate_policy, rate_class, observed_requests=0)
        if not decision.allowed:
            raise BrokerRateLimitError(f"read-only rate policy blocked: {decision.reason}")
        path = self._profile.endpoint(resource)
        if path is None:
            raise BrokerAdapterUnavailableError(f"read endpoint unavailable: {resource}")
        try:
            response = self._transport.get(path)
        except (BrokerRateLimitError, BrokerAuthError, BrokerNetworkError):
            raise
        except Exception:
            raise BrokerNetworkError("read-only broker transport unavailable") from None
        if not isinstance(response, dict):
            raise BrokerAdapterUnavailableError(f"invalid broker response for {resource}")
        if response.get("status") is False:
            raise BrokerAdapterUnavailableError(f"broker reported unavailable {resource}")
        if "data" not in response or response.get("data") is None:
            raise BrokerAdapterUnavailableError(f"partial broker response for {resource}")
        return response["data"]

    @staticmethod
    def _status(raw: object) -> BrokerAdapterOrderStatus:
        token = str(raw or "").strip().lower()
        canonical = _ANGEL_STATUS_TO_CANONICAL.get(token)
        return map_raw_status(canonical)

    def orders(self) -> tuple[BrokerAdapterOrderSnapshot, ...]:
        raw = self._read("orders", BrokerRateClass.READ_ORDERS)
        if not isinstance(raw, list):
            raise BrokerAdapterUnavailableError("orders payload must be a list")
        observed_at = self._now()
        result: list[BrokerAdapterOrderSnapshot] = []
        for item in raw:
            if not isinstance(item, dict):
                raise BrokerAdapterUnavailableError("invalid order payload item")
            broker_id = _text(item.get("orderid"), "order id")
            local_id_raw = item.get("client_order_id") or item.get("ordertag")
            local_id = str(local_id_raw).strip() if local_id_raw else f"FOREIGN:{broker_id}"
            ordered = _decimal(item.get("quantity"), "order quantity")
            filled = _decimal(item.get("filledshares", 0), "filled quantity")
            fragment_count_raw = item.get("fill_fragment_count", 0)
            try:
                fragment_count = int(fragment_count_raw)
            except (TypeError, ValueError):
                raise BrokerAdapterUnavailableError("invalid fill fragment count") from None
            if filled > 0 and fragment_count <= 0:
                raise BrokerAdapterUnavailableError("filled order lacks fragment evidence")
            status = self._status(item.get("orderstatus") or item.get("status"))
            result.append(
                BrokerAdapterOrderSnapshot(
                    order_id=local_id,
                    broker_order_identity=broker_id,
                    adapter_status=status,
                    ordered_quantity=ordered,
                    cumulative_filled_quantity=filled,
                    fragment_count=fragment_count,
                    last_observation_sequence=int(item.get("observation_sequence", 0)),
                    last_observed_at=observed_at,
                    raw_status_token=str(item.get("orderstatus") or item.get("status") or "UNKNOWN"),
                )
            )
        return tuple(result)

    def trades(self) -> tuple[BrokerFillFragment, ...]:
        raw = self._read("trades", BrokerRateClass.READ_ORDERS)
        if not isinstance(raw, list):
            raise BrokerAdapterUnavailableError("trades payload must be a list")
        observed_at = self._now()
        result: list[BrokerFillFragment] = []
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                raise BrokerAdapterUnavailableError("invalid trade payload item")
            broker_id = _text(item.get("orderid"), "trade order id")
            local_id_raw = item.get("client_order_id") or item.get("ordertag")
            local_id = str(local_id_raw).strip() if local_id_raw else f"FOREIGN:{broker_id}"
            result.append(
                BrokerFillFragment(
                    order_id=local_id,
                    broker_order_identity=broker_id,
                    broker_fill_id=_text(item.get("tradeid") or item.get("fillid"), "trade fill id"),
                    fill_quantity=_decimal(item.get("fillsize") or item.get("quantity"), "trade quantity"),
                    fill_price=_decimal(item.get("fillprice") or item.get("price"), "trade price"),
                    observed_at=observed_at,
                    observation_sequence=int(item.get("observation_sequence", index)),
                )
            )
        return tuple(result)

    def positions(self) -> tuple[BrokerPositionSnapshot, ...]:
        raw = self._read("positions", BrokerRateClass.READ_ACCOUNT)
        if not isinstance(raw, list):
            raise BrokerAdapterUnavailableError("positions payload must be a list")
        observed_at = self._now()
        result: list[BrokerPositionSnapshot] = []
        for item in raw:
            if not isinstance(item, dict):
                raise BrokerAdapterUnavailableError("invalid position payload item")
            result.append(
                BrokerPositionSnapshot(
                    instrument_token=_text(item.get("symboltoken"), "position instrument token"),
                    trading_symbol=_text(item.get("tradingsymbol"), "position trading symbol"),
                    quantity=_decimal(item.get("netqty", 0), "position quantity"),
                    average_price=_decimal(item.get("avgnetprice", 0), "position average price"),
                    product_type=_text(item.get("producttype"), "position product type"),
                    observed_at=observed_at,
                    current_price=_decimal(item.get("ltp"), "position current price") if item.get("ltp") is not None else None,
                    pnl=_decimal(item.get("pnl"), "position pnl") if item.get("pnl") is not None else None,
                )
            )
        return tuple(result)

    def funds(self) -> BrokerFundsSnapshot:
        raw = self._read("funds", BrokerRateClass.READ_ACCOUNT)
        if not isinstance(raw, dict):
            raise BrokerAdapterUnavailableError("funds payload must be an object")
        return BrokerFundsSnapshot(
            available_balance=_decimal(raw.get("availablecash"), "available balance"),
            used_margin=_decimal(raw.get("utiliseddebits", 0), "used margin"),
            total_equity=_decimal(raw.get("net"), "total equity"),
            observed_at=self._now(),
            currency=str(raw.get("currency") or "INR"),
        )

    def health(self) -> AngelOneReadOnlyHealth:
        session = self._session.health()
        return AngelOneReadOnlyHealth(
            session_state=session.state.value,
            broker_truth_available=session.observation_available,
            profile_ref=self._profile.reference,
            rule_evidence_ref=self._rule_evidence.reference,
        )

    def query_open_orders(self) -> tuple[BrokerAdapterOrderSnapshot, ...]:
        return tuple(item for item in self.orders() if not item.adapter_status.is_terminal)

    def query_order(self, order_id: str) -> BrokerAdapterOrderSnapshot | None:
        identity = str(order_id or "").strip()
        if not identity:
            raise ValueError("order_id must be non-empty")
        for item in self.orders():
            if item.order_id == identity or item.broker_order_identity == identity:
                return item
        return None

    def query_positions(self) -> tuple[BrokerPositionSnapshot, ...]:
        return self.positions()

    def query_funds(self) -> BrokerFundsSnapshot:
        return self.funds()


__all__ = ["AngelOneReadOnlyAdapter"]
