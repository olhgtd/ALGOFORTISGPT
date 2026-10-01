from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib import import_module

import pytest


def _api():
    try:
        return import_module('engine.ai.v2.memory')
    except ModuleNotFoundError:
        pytest.fail('engine.ai.v2.memory is missing', pytrace=False)


def _contracts():
    return import_module('engine.ai.v2.contracts')


class Audit:
    def __init__(self): self.events=[]
    def __call__(self, event): self.events.append(event)


def test_cross_user_isolation_on_read_and_same_item_id():
    api=_api(); c=_contracts(); repo=api.InMemoryMemoryRepository(); audit=Audit(); svc=api.MemoryService(repo, audit)
    now=datetime(2026,9,27,5,30,tzinfo=timezone.utc)
    svc.store(user_id='u1', item_id='pref', value='research note', provenance_ref='src:1', data_class=c.DataClass.STRATEGY_RESEARCH, policy_ref='memory/v1', now=now)
    svc.store(user_id='u2', item_id='pref', value='other note', provenance_ref='src:2', data_class=c.DataClass.STRATEGY_RESEARCH, policy_ref='memory/v1', now=now)
    assert svc.get('u1','pref').value == 'research note'
    assert svc.get('u2','pref').value == 'other note'
    assert svc.get('u3','pref') is None


@pytest.mark.parametrize('name',["BROKER_CREDENTIAL","BROKER_ACCOUNT_IDENTIFIER","PERSONAL_DATA","RAW_TRADE_LOG","PRIVATE_KEY","UNKNOWN"])
def test_forbidden_memory_classes_are_rejected(name):
    api=_api(); c=_contracts(); svc=api.MemoryService(api.InMemoryMemoryRepository(), Audit())
    with pytest.raises(api.MemoryPolicyError):
        svc.store(user_id='u1', item_id='x', value='secret', provenance_ref='src', data_class=getattr(c.DataClass,name), policy_ref='memory/v1', now=datetime(2026,9,27,tzinfo=timezone.utc))


def test_missing_provenance_or_classification_is_rejected():
    api=_api(); c=_contracts(); svc=api.MemoryService(api.InMemoryMemoryRepository(), Audit()); now=datetime(2026,9,27,tzinfo=timezone.utc)
    with pytest.raises(api.MemoryPolicyError):
        svc.store(user_id='u1', item_id='x', value='v', provenance_ref='', data_class=c.DataClass.MARKET_RESEARCH, policy_ref='memory/v1', now=now)
    with pytest.raises(api.MemoryPolicyError):
        svc.store(user_id='u1', item_id='x', value='v', provenance_ref='src', data_class=None, policy_ref='memory/v1', now=now)


def test_correction_creates_versioned_replacement_and_audit_has_no_payload():
    api=_api(); c=_contracts(); repo=api.InMemoryMemoryRepository(); audit=Audit(); svc=api.MemoryService(repo,audit); now=datetime(2026,9,27,tzinfo=timezone.utc)
    first=svc.store(user_id='u1', item_id='x', value='old', provenance_ref='src:1', data_class=c.DataClass.NEWS_RESEARCH, policy_ref='memory/v1', now=now)
    second=svc.correct(user_id='u1', item_id='x', value='new', provenance_ref='src:2', now=now+timedelta(minutes=1))
    assert first.version == 1 and second.version == 2
    assert svc.get('u1','x').value == 'new'
    assert audit.events[-1].action == 'CORRECT'
    assert not hasattr(audit.events[-1], 'value')
    assert 'new' not in repr(audit.events[-1])


def test_delete_removes_from_active_retrieval_without_payload_in_audit():
    api=_api(); c=_contracts(); repo=api.InMemoryMemoryRepository(); audit=Audit(); svc=api.MemoryService(repo,audit); now=datetime(2026,9,27,tzinfo=timezone.utc)
    svc.store(user_id='u1', item_id='x', value='sensitive-ish research text', provenance_ref='src', data_class=c.DataClass.MARKET_RESEARCH, policy_ref='memory/v1', now=now)
    svc.delete(user_id='u1', item_id='x', now=now+timedelta(minutes=1))
    assert svc.get('u1','x') is None
    assert audit.events[-1].action == 'DELETE'
    assert 'sensitive-ish' not in repr(audit.events[-1])


def test_provider_output_cannot_persist_without_policy_validation():
    api=_api(); c=_contracts(); svc=api.MemoryService(api.InMemoryMemoryRepository(), Audit()); now=datetime(2026,9,27,tzinfo=timezone.utc)
    with pytest.raises(api.MemoryPolicyError):
        svc.store_provider_output(user_id='u1', item_id='x', value='model says remember me', provenance_ref='provider:p1', data_class=c.DataClass.STRATEGY_RESEARCH, policy_ref='', now=now)
