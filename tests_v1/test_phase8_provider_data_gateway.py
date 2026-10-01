from datetime import datetime, timedelta, timezone
import pytest
from engine.ai.v2.contracts import AIRequest, DataClass, ProviderKind, ProviderManifest
from engine.data import licensing as l

NOW=datetime(2026,9,27,4,30,tzinfo=timezone.utc)


def manifest(kind=ProviderKind.CLOUD):
    return ProviderManifest('cloud-a' if kind is ProviderKind.CLOUD else 'local-a',kind,'1.0.0','model-a',('research/v1',),('MARKET_RESEARCH','DATASET_DERIVED','NEWS_RESEARCH','STRATEGY_RESEARCH'), 'retention:approved' if kind is ProviderKind.CLOUD else None,False)

def metadata(ext=None):
    if ext is None:
        ext=l.ExternalProcessingPermission.ALLOWED
    return l.DataLicenceMetadata('feed-a','terms-v4',l.AcquisitionPermission.ALLOWED,(l.DataUse.RESEARCH,),False,ext)

def request(data_classes=(DataClass.MARKET_RESEARCH,), payload=None):
    return AIRequest('r1','research/v1',data_classes,payload or {'symbol':'NIFTY','note':'safe'},('dataset:d1',))

def evidence(ext=None, *, stale=False, ambiguous=False):
    if ext is None:
        ext=l.ExternalProcessingPermission.ALLOWED
    from engine.ai.v2.data_policy import DataProvenanceEvidence
    return DataProvenanceEvidence('prov:1',metadata(ext),NOW-timedelta(minutes=1), NOW-timedelta(seconds=1) if stale else NOW+timedelta(hours=1), ambiguous)

def policy(provider_id='cloud-a'):
    from engine.ai.v2.data_policy import ProviderDataPolicy
    return ProviderDataPolicy('ai-data/v1',provider_id,'1.0.0',(DataClass.MARKET_RESEARCH,DataClass.DATASET_DERIVED,DataClass.NEWS_RESEARCH,DataClass.STRATEGY_RESEARCH))

def gateway(events):
    from engine.ai.v2.provider_gateway import ProviderDataGateway
    return ProviderDataGateway(licence_policy=l.DataLicencePolicy(), audit_sink=events.append, clock=lambda:NOW)


def test_cloud_requires_positive_fresh_unambiguous_external_processing_evidence():
    from engine.ai.v2.provider_gateway import ProviderGatewayDenied
    for ev in (evidence(l.ExternalProcessingPermission.UNKNOWN), evidence(l.ExternalProcessingPermission.PROHIBITED), evidence(stale=True), evidence(ambiguous=True)):
        with pytest.raises(ProviderGatewayDenied): gateway([]).prepare(request(), provider=manifest(), policy=policy(), provenance=(ev,))
    with pytest.raises(ProviderGatewayDenied): gateway([]).prepare(request(), provider=manifest(), policy=policy(), provenance=())


def test_redaction_does_not_override_licensing_denial_and_transport_ready_payload_has_no_canary():
    from engine.ai.v2.provider_gateway import ProviderGatewayDenied
    payload={'symbol':'NIFTY','api_token':'CANARY_SECRET','nested':{'account_id':'ACC123','comment':'ok'}}
    with pytest.raises(ProviderGatewayDenied): gateway([]).prepare(request(payload=payload),provider=manifest(),policy=policy(),provenance=(evidence(l.ExternalProcessingPermission.PROHIBITED),))
    events=[]; ready=gateway(events).prepare(request(payload=payload),provider=manifest(),policy=policy(),provenance=(evidence(),))
    assert 'CANARY_SECRET' not in repr(ready.sanitized_payload)
    assert 'ACC123' not in repr(ready.sanitized_payload)
    assert 'CANARY_SECRET' not in repr(events) and 'ACC123' not in repr(events)
    assert ready.sanitized_payload['nested']['comment']=='ok'


def test_forbidden_or_unknown_data_classes_are_denied():
    from engine.ai.v2.provider_gateway import ProviderGatewayDenied
    for cls in (DataClass.BROKER_CREDENTIAL,DataClass.BROKER_ACCOUNT_IDENTIFIER,DataClass.PERSONAL_DATA,DataClass.RAW_TRADE_LOG,DataClass.PRIVATE_KEY,DataClass.UNKNOWN):
        with pytest.raises(ProviderGatewayDenied): gateway([]).prepare(request((cls,)),provider=manifest(),policy=policy(),provenance=(evidence(),))


def test_local_does_not_require_cloud_egress_permission_but_still_requires_research_use():
    local=manifest(ProviderKind.LOCAL); local_policy=policy('local-a')
    ready=gateway([]).prepare(request(),provider=local,policy=local_policy,provenance=(evidence(l.ExternalProcessingPermission.PROHIBITED),))
    assert ready.provider_id=='local-a'
    bad=l.DataLicenceMetadata('feed-a','terms',l.AcquisitionPermission.ALLOWED,(l.DataUse.BACKTEST,),False,l.ExternalProcessingPermission.PROHIBITED)
    from engine.ai.v2.data_policy import DataProvenanceEvidence
    bad_ev=DataProvenanceEvidence('prov:bad',bad,NOW-timedelta(minutes=1),NOW+timedelta(hours=1),False)
    from engine.ai.v2.provider_gateway import ProviderGatewayDenied
    with pytest.raises(ProviderGatewayDenied): gateway([]).prepare(request(),provider=local,policy=local_policy,provenance=(bad_ev,))


def test_audit_failure_blocks_preparation_and_fingerprint_is_repeatable():
    from engine.ai.v2.provider_gateway import ProviderDataGateway, ProviderGatewayDenied
    def broken(_): raise RuntimeError('audit down')
    g=ProviderDataGateway(licence_policy=l.DataLicencePolicy(),audit_sink=broken,clock=lambda:NOW)
    with pytest.raises(ProviderGatewayDenied): g.prepare(request(),provider=manifest(),policy=policy(),provenance=(evidence(),))
    a=gateway([]).prepare(request(),provider=manifest(),policy=policy(),provenance=(evidence(),))
    b=gateway([]).prepare(request(),provider=manifest(),policy=policy(),provenance=(evidence(),))
    assert a.outbound_fingerprint==b.outbound_fingerprint
