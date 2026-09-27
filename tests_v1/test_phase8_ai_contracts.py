from datetime import datetime, timedelta, timezone
from dataclasses import fields, FrozenInstanceError
import pytest


def test_contracts_reject_blank_and_bad_versions():
    from engine.ai.v2.contracts import ProviderKind, ProviderManifest, AIContractError
    with pytest.raises(AIContractError):
        ProviderManifest('', ProviderKind.LOCAL, '1.0.0', 'model', ('trade_candidate/v1',), ('MARKET_RESEARCH',), None, False)
    with pytest.raises(AIContractError):
        ProviderManifest('local', ProviderKind.LOCAL, 'v1', 'model', ('trade_candidate/v1',), ('MARKET_RESEARCH',), None, False)


def test_candidate_is_frozen_ttl_bound_and_non_executable():
    from engine.ai.v2.contracts import TradeCandidate, TradeCandidateAction, AIContractError
    now = datetime(2026, 9, 27, tzinfo=timezone.utc)
    kwargs = dict(candidate_id='c1', context_ref='research:r1', instrument_ref='NSE:NIFTY:CE',
        action=TradeCandidateAction.BUY_CE, created_at=now, valid_until=now+timedelta(minutes=1),
        input_fingerprint='f'*64, provider_id='local', model_id='m1', agent_id='research',
        schema_version='trade-candidate/v1', provenance_refs=('dataset:d1',), rationale_refs=('note:n1',))
    c = TradeCandidate(**kwargs)
    with pytest.raises(FrozenInstanceError):
        c.action = TradeCandidateAction.HOLD
    names = {f.name for f in fields(TradeCandidate)}
    assert {'approved_order','broker_order_id','arm_live','hard_risk_override','quantity'}.isdisjoint(names)
    with pytest.raises(AIContractError):
        TradeCandidate(**{**kwargs, 'created_at': now.replace(tzinfo=None)})
    with pytest.raises(AIContractError):
        TradeCandidate(**{**kwargs, 'valid_until': now})


def test_response_and_request_require_schema_model_and_provenance():
    from engine.ai.v2.contracts import AIRequest, AIResponse, DataClass, AIContractError
    with pytest.raises(AIContractError):
        AIRequest('r1','', (DataClass.MARKET_RESEARCH,), 'x', ('p',))
    with pytest.raises(AIContractError):
        AIResponse('r1','provider','', 'trade-candidate/v1', {}, ('p',), 'f'*64)
