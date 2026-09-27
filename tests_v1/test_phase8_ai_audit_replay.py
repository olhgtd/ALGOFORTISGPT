from __future__ import annotations
from datetime import datetime, timezone
from importlib import import_module
import pytest


def _audit():
    try: return import_module('engine.ai.v2.audit')
    except ModuleNotFoundError: pytest.fail('engine.ai.v2.audit is missing', pytrace=False)

def _replay():
    try: return import_module('engine.ai.v2.replay')
    except ModuleNotFoundError: pytest.fail('engine.ai.v2.replay is missing', pytrace=False)


def _event(api, seq=1):
    return api.AIAuditEvent.create(action='PROVIDER_DISPATCH', correlation_id='corr-1', sequence=seq,
        provider_id='cloud', model_id='m1', tool_id=None, policy_ref='policy/v1', licensing_ref='lic:1',
        input_fingerprint='a'*64, output_fingerprint='b'*64, status='SUCCESS',
        occurred_at=datetime(2026,9,27,6,30,tzinfo=timezone.utc))


def test_audit_failure_blocks_policy_sensitive_action_before_side_effect():
    api=_audit(); calls=[]
    def bad_sink(event): raise RuntimeError('down')
    runner=api.AuditedAction(bad_sink)
    with pytest.raises(api.AIAuditError): runner.run(_event(api), lambda: calls.append('called'))
    assert calls == []


def test_audit_event_contains_safe_refs_and_no_raw_payload_fields():
    api=_audit(); event=_event(api)
    names=set(event.__dataclass_fields__)
    assert {'provider_id','model_id','policy_ref','licensing_ref','input_fingerprint','output_fingerprint','correlation_id'} <= names
    assert {'payload','raw_payload','secret','account_id','trade_log'}.isdisjoint(names)
    assert 'canary-secret' not in repr(event)


def test_replay_reconstructs_immutable_ordered_chain_without_execution_api():
    a=_audit(); r=_replay(); events=(_event(a,2),_event(a,1))
    chain=r.replay(events)
    assert [step.sequence for step in chain.steps] == [1,2]
    assert chain.correlation_id == 'corr-1'
    assert {'place_order','submit_order','arm_live','mutate_broker'}.isdisjoint(set(dir(chain)))
    with pytest.raises(Exception): chain.correlation_id='other'


def test_replay_rejects_mixed_correlation_or_duplicate_sequence():
    a=_audit(); r=_replay(); first=_event(a,1)
    mixed=a.AIAuditEvent.create(action='X',correlation_id='corr-2',sequence=2,provider_id='p',model_id='m',tool_id=None,policy_ref='p',licensing_ref='l',input_fingerprint='a'*64,output_fingerprint=None,status='FAILED',occurred_at=datetime(2026,9,27,6,31,tzinfo=timezone.utc))
    with pytest.raises(r.ReplayError): r.replay((first,mixed))
    with pytest.raises(r.ReplayError): r.replay((first,first))
