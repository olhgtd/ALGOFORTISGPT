from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib import import_module

import pytest


def _api():
    try: return import_module('engine.ai.v2.shadow')
    except ModuleNotFoundError: pytest.fail('engine.ai.v2.shadow is missing', pytrace=False)

def _deps():
    return import_module('engine.ai.v2.contracts'), import_module('engine.ai.v2.candidates')

def _candidate(c, now):
    return c.TradeCandidate('c1','research:r1','NSE:NIFTY:CE',c.TradeCandidateAction.BUY_CE,now,now+timedelta(minutes=2),'f'*64,'local','m1','research','trade-candidate/v1',('dataset:d1',),('note:n1',),now+timedelta(minutes=1))

def _valid(c,v):
    return v.CandidateValidationResult(c.CandidateValidationVerdict.VALID,(),c.TradeCandidateAction.BUY_CE,'a'*64)


def test_shadow_path_has_no_order_submission_or_promotion_api():
    api=_api()
    forbidden={'submit_order','place_order','approved_order','promote','set_provider_route','arm_live'}
    assert forbidden.isdisjoint(set(dir(api.ShadowLedger)))
    assert forbidden.isdisjoint(api.ShadowRecord.__dataclass_fields__)


def test_stale_candidate_is_recorded_as_no_trade_not_active_recommendation():
    api=_api(); c,v=_deps(); now=datetime(2026,9,27,6,tzinfo=timezone.utc); ledger=api.ShadowLedger()
    candidate=_candidate(c,now)
    result=v.CandidateValidationResult(c.CandidateValidationVerdict.NO_TRADE,(c.NoTradeReason.STALE_CANDIDATE,),c.TradeCandidateAction.HOLD,'b'*64)
    record=ledger.record(candidate=candidate,validation=result,challenger_verdict='PASS',policy_ref='candidate/v1',licensing_ref='lic:1',audit_ref='audit:1',provider_version='1.0.0',model_version='m1',agent_version='research/1',observed_at=now)
    assert record.status is api.ShadowStatus.NO_TRADE
    assert record.effective_action is c.TradeCandidateAction.HOLD


def test_same_safe_evidence_produces_deterministic_record_id():
    api=_api(); c,v=_deps(); now=datetime(2026,9,27,6,tzinfo=timezone.utc); candidate=_candidate(c,now); result=_valid(c,v)
    kwargs=dict(candidate=candidate,validation=result,challenger_verdict='PASS',policy_ref='candidate/v1',licensing_ref='lic:1',audit_ref='audit:1',provider_version='1.0.0',model_version='m1',agent_version='research/1',observed_at=now)
    first=api.ShadowLedger().record(**kwargs); second=api.ShadowLedger().record(**kwargs)
    assert first.record_id == second.record_id


def test_later_outcome_is_append_only_and_does_not_rewrite_record():
    api=_api(); c,v=_deps(); now=datetime(2026,9,27,6,tzinfo=timezone.utc); ledger=api.ShadowLedger(); candidate=_candidate(c,now)
    record=ledger.record(candidate=candidate,validation=_valid(c,v),challenger_verdict='PASS',policy_ref='candidate/v1',licensing_ref='lic:1',audit_ref='audit:1',provider_version='1.0.0',model_version='m1',agent_version='research/1',observed_at=now)
    before=repr(record)
    outcome=ledger.attach_outcome(record_id=record.record_id,outcome_ref='outcome:close',metrics_ref='metrics:1',observed_at=now+timedelta(hours=1))
    assert repr(ledger.get_record(record.record_id)) == before
    assert ledger.outcomes(record.record_id) == (outcome,)


def test_missing_policy_licensing_or_provenance_blocks_valid_classification():
    api=_api(); c,v=_deps(); now=datetime(2026,9,27,6,tzinfo=timezone.utc); ledger=api.ShadowLedger(); candidate=_candidate(c,now); result=_valid(c,v)
    for field in ('policy_ref','licensing_ref','audit_ref'):
        kwargs=dict(candidate=candidate,validation=result,challenger_verdict='PASS',policy_ref='candidate/v1',licensing_ref='lic:1',audit_ref='audit:1',provider_version='1.0.0',model_version='m1',agent_version='research/1',observed_at=now)
        kwargs[field]=''
        with pytest.raises(api.ShadowPolicyError): ledger.record(**kwargs)
    with pytest.raises(c.AIContractError):
        c.TradeCandidate(candidate.candidate_id,candidate.context_ref,candidate.instrument_ref,candidate.action,candidate.created_at,candidate.valid_until,candidate.input_fingerprint,candidate.provider_id,candidate.model_id,candidate.agent_id,candidate.schema_version,(),candidate.rationale_refs,candidate.input_data_valid_until)
