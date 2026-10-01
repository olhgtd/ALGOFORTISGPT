from __future__ import annotations
from importlib import import_module
import pytest


def _api():
    try: return import_module('engine.ai.v2.audit')
    except ModuleNotFoundError: pytest.fail('engine.ai.v2.audit is missing', pytrace=False)


class Router:
    def __init__(self, selected=None, fail=False): self.selected=selected; self.fail=fail
    def select(self, **kwargs):
        if self.fail: raise RuntimeError('provider unavailable and no approved compatible fallback')
        return self.selected


class Binding:
    def __init__(self, provider_id):
        self.provider_manifest=type('M',(),{'provider_id':provider_id})()


def test_no_approved_fallback_returns_no_trade_and_never_invokes():
    api=_api(); calls=[]
    dispatch=api.FailClosedProviderDispatch(router=Router(fail=True), prepare=lambda binding: object(), invoke=lambda ready: calls.append('invoke'), audit_sink=lambda e: None)
    result=dispatch.execute(provider_id='primary', schema_id='trade-candidate/v1', data_classes=('MARKET_RESEARCH',), snapshots={})
    assert result.status is api.DispatchStatus.NO_TRADE
    assert calls == []


def test_fallback_still_must_pass_gateway_prepare_before_invoke():
    api=_api(); calls=[]
    dispatch=api.FailClosedProviderDispatch(router=Router(Binding('fallback')), prepare=lambda binding: (_ for _ in ()).throw(RuntimeError('licensing denied')), invoke=lambda ready: calls.append('invoke'), audit_sink=lambda e: None)
    result=dispatch.execute(provider_id='primary', schema_id='trade-candidate/v1', data_classes=('MARKET_RESEARCH',), snapshots={})
    assert result.status is api.DispatchStatus.NO_TRADE
    assert calls == []


def test_approved_compatible_fallback_is_audited_before_single_invoke():
    api=_api(); order=[]
    dispatch=api.FailClosedProviderDispatch(router=Router(Binding('fallback')), prepare=lambda binding: {'provider_id':binding.provider_manifest.provider_id}, invoke=lambda ready: order.append(('invoke',ready['provider_id'])) or 'ok', audit_sink=lambda e: order.append(('audit',e.provider_id)))
    result=dispatch.execute(provider_id='primary', schema_id='trade-candidate/v1', data_classes=('MARKET_RESEARCH',), snapshots={})
    assert result.status is api.DispatchStatus.DISPATCHED
    assert result.selected_provider_id == 'fallback'
    assert order == [('audit','fallback'),('invoke','fallback')]
