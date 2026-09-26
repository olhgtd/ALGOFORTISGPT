from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import importlib
from pathlib import Path

import pytest

from engine.broker_adapters.contracts import (
    BrokerAdapterOrderSnapshot,
    BrokerAdapterOrderStatus,
    BrokerAdapterUnavailableError,
    BrokerAuthError,
    BrokerFundsSnapshot,
    BrokerNetworkError,
    BrokerPositionSnapshot,
    BrokerRateLimitError,
)
from engine.broker_adapters.angelone_v2.contracts import (
    AngelOneBrokerProfile,
    AngelOneCredentialRef,
    BrokerRuleEvidenceRef,
)
from engine.broker_adapters.angelone_v2.rate_policy import BrokerRateClass, BrokerRatePolicy, BrokerRateRule
from engine.broker_adapters.angelone_v2.session import AngelOneSessionAuthority

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "engine" / "broker_adapters" / "angelone_v2" / "read_only_adapter.py"


def _load():
    assert MODULE.is_file(), "Phase-6 Angel One read-only adapter is missing"
    return importlib.import_module("engine.broker_adapters.angelone_v2.read_only_adapter")


def _now():
    return datetime(2026, 9, 27, 4, 0, tzinfo=timezone.utc)


class Clock:
    def now(self): return _now()


class AuthTransport:
    def authenticate(self, *, profile, credential_ref):
        return {"access_token":"a","refresh_token":"r","expires_at":_now()+timedelta(hours=1),"daily_valid_until":_now()+timedelta(hours=8)}
    def refresh(self, **kwargs):
        return self.authenticate(profile=kwargs["profile"], credential_ref=kwargs["credential_ref"])


class ReadTransport:
    def __init__(self, payloads=None, error=None):
        self.payloads = payloads or {}
        self.error = error
        self.paths=[]
    def get(self, path):
        self.paths.append(path)
        if self.error: raise self.error
        return self.payloads.get(path)


def _profile(*, endpoints=True):
    kwargs = {}
    if endpoints:
        kwargs["read_endpoints"] = (
            ("orders", "/orders"), ("trades", "/trades"), ("positions", "/positions"), ("funds", "/funds")
        )
    return AngelOneBrokerProfile("ANGELONE/SMARTAPI/READ_ONLY","2026-09-27","https://apiconnect.angelone.in","docs", **kwargs)


def _session(profile):
    s=AngelOneSessionAuthority(profile=profile, credential_ref=AngelOneCredentialRef("secret://x","acct"), transport=AuthTransport(), clock=Clock())
    s.authenticate(); return s


def _policy():
    return BrokerRatePolicy(
        "TEST_ONLY/G6/RATE","v1",
        {
            BrokerRateClass.READ_ORDERS: BrokerRateRule(5,1),
            BrokerRateClass.READ_ACCOUNT: BrokerRateRule(5,1),
        },
        test_only=True,
    )


def _rule_ref():
    return BrokerRuleEvidenceRef("G6-RULES","v1",_now(),("angel","nse"))


def _adapter(transport, profile=None):
    m=_load(); p=profile or _profile()
    return m.AngelOneReadOnlyAdapter(profile=p, session_authority=_session(p), transport=transport, rate_policy=_policy(), rule_evidence=_rule_ref(), clock=Clock())


def test_production_object_has_no_callable_mutation_methods() -> None:
    a=_adapter(ReadTransport({"/orders":{"status":True,"data":[]},"/trades":{"status":True,"data":[]},"/positions":{"status":True,"data":[]},"/funds":{"status":True,"data":{"availablecash":"1","utiliseddebits":"0","net":"1"}}}))
    for name in ("place","submit","modify","cancel","create_gtt","modify_gtt","cancel_gtt"):
        assert not callable(getattr(a,name,None)), name


def test_endpoint_profile_is_injected_and_missing_endpoint_fails_closed() -> None:
    p=_profile()
    t=ReadTransport({"/orders":{"status":True,"data":[]}})
    a=_adapter(t,p)
    assert a.profile().api_base_url == "https://apiconnect.angelone.in"
    assert a.orders() == ()
    assert t.paths == ["/orders"]

    p2=_profile(endpoints=False)
    a2=_adapter(ReadTransport(),p2)
    with pytest.raises(BrokerAdapterUnavailableError, match="endpoint"):
        a2.orders()
    assert "apiconnect.angelbroking.com" not in MODULE.read_text(encoding="utf-8")


def test_partial_or_invalid_broker_response_fails_typed_unavailable() -> None:
    a=_adapter(ReadTransport({"/orders":{"status":True}}))
    with pytest.raises(BrokerAdapterUnavailableError):
        a.orders()
    b=_adapter(ReadTransport({"/positions":None}))
    with pytest.raises(BrokerAdapterUnavailableError):
        b.positions()


def test_orders_positions_and_funds_normalize_to_existing_canonical_contracts() -> None:
    payloads={
        "/orders":{"status":True,"data":[{"orderid":"B1","client_order_id":"L1","orderstatus":"open","quantity":"2","filledshares":"0"}]},
        "/positions":{"status":True,"data":[{"symboltoken":"26000","tradingsymbol":"NIFTY","netqty":"1","avgnetprice":"100","producttype":"INTRADAY","ltp":"101","pnl":"1"}]},
        "/funds":{"status":True,"data":{"availablecash":"1000","utiliseddebits":"100","net":"1100"}},
    }
    a=_adapter(ReadTransport(payloads))
    orders=a.orders(); positions=a.positions(); funds=a.funds()
    assert isinstance(orders[0], BrokerAdapterOrderSnapshot)
    assert orders[0].adapter_status is BrokerAdapterOrderStatus.ACCEPTED
    assert orders[0].broker_order_identity == "B1"
    assert isinstance(positions[0], BrokerPositionSnapshot)
    assert positions[0].quantity == Decimal("1")
    assert isinstance(funds, BrokerFundsSnapshot)
    assert funds.available_balance == Decimal("1000")


@pytest.mark.parametrize("error", [BrokerRateLimitError("429"), BrokerAuthError("401"), BrokerNetworkError("down")])
def test_typed_transport_failures_are_not_converted_to_empty_success(error) -> None:
    a=_adapter(ReadTransport(error=error))
    with pytest.raises(type(error)):
        a.orders()
