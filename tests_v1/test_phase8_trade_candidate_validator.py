from dataclasses import fields,replace
from datetime import datetime,timedelta,timezone
from engine.ai.v2.contracts import TradeCandidate,TradeCandidateAction
NOW=datetime(2026,9,27,5,30,tzinfo=timezone.utc)

def candidate(action=TradeCandidateAction.BUY_CE,*,valid=60,data_valid=120,instrument='NSE:NIFTY:CE',schema='trade-candidate/v1'):
 return TradeCandidate(candidate_id='c1',context_ref='research:r1',instrument_ref=instrument,action=action,created_at=NOW-timedelta(seconds=30),valid_until=NOW+timedelta(seconds=valid),input_fingerprint='a'*64,provider_id='local-a',model_id='m',agent_id='research',schema_version=schema,provenance_refs=('dataset:d1',),rationale_refs=('note:n1',),input_data_valid_until=None if data_valid is None else NOW+timedelta(seconds=data_valid))
def validator(now=NOW):
 from engine.ai.v2.candidates import CandidatePolicy,TradeCandidateValidator
 return TradeCandidateValidator(lambda:now,CandidatePolicy('candidate-policy/v1',('trade-candidate/v1',),('NIFTY','BANKNIFTY')))

def test_now_at_or_after_candidate_ttl_is_hard_stale_no_trade():
 from engine.ai.v2.contracts import CandidateValidationVerdict,NoTradeReason
 c=candidate(valid=0)
 r=validator().validate(c)
 assert r.verdict is CandidateValidationVerdict.NO_TRADE and NoTradeReason.STALE_CANDIDATE in r.reasons

def test_missing_or_stale_input_data_fails_closed():
 from engine.ai.v2.contracts import CandidateValidationVerdict,NoTradeReason
 assert NoTradeReason.STALE_INPUT_DATA in validator().validate(candidate(data_valid=None)).reasons
 assert NoTradeReason.STALE_INPUT_DATA in validator().validate(candidate(data_valid=0)).reasons

def test_schema_instrument_and_action_scope_are_deterministic():
 from engine.ai.v2.contracts import NoTradeReason
 assert NoTradeReason.UNSUPPORTED_SCHEMA in validator().validate(candidate(schema='other/v1')).reasons
 assert NoTradeReason.INSTRUMENT_OUT_OF_SCOPE in validator().validate(candidate(instrument='NSE:FINNIFTY:CE')).reasons
 assert NoTradeReason.ACTION_INSTRUMENT_MISMATCH in validator().validate(candidate(action=TradeCandidateAction.BUY_PE,instrument='NSE:NIFTY:CE')).reasons

def test_buy_hypothesis_never_becomes_order_and_hold_is_no_trade():
 from engine.ai.v2.contracts import CandidateValidationVerdict,NoTradeReason
 buy=validator().validate(candidate()); hold=validator().validate(candidate(action=TradeCandidateAction.HOLD,instrument='NSE:NIFTY:CE'))
 assert buy.verdict is CandidateValidationVerdict.VALID
 assert hold.verdict is CandidateValidationVerdict.NO_TRADE and NoTradeReason.HOLD_REQUESTED in hold.reasons
 assert {'approved_order','order_intent','quantity','broker_order_id'}.isdisjoint({f.name for f in fields(type(buy))})

def test_same_candidate_policy_time_has_same_verdict_fingerprint():
 a=validator().validate(candidate());b=validator().validate(candidate())
 assert a.fingerprint==b.fingerprint
