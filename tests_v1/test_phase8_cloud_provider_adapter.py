from datetime import datetime,timedelta,timezone
import pytest
from engine.ai.v2.contracts import AIRequest,DataClass,ProviderKind,ProviderManifest
from engine.data import licensing as l
NOW=datetime(2026,9,27,5,0,tzinfo=timezone.utc)

def manifest(): return ProviderManifest('cloud-a',ProviderKind.CLOUD,'1.0.0','cloud-model',('research/v1',),('MARKET_RESEARCH',),'retention:ok',False)
def raw_request(payload=None): return AIRequest('r1','research/v1',(DataClass.MARKET_RESEARCH,),payload or {'symbol':'NIFTY'},('dataset:d1',))
def ready(events=None,payload=None):
 from engine.ai.v2.data_policy import DataProvenanceEvidence,ProviderDataPolicy
 from engine.ai.v2.provider_gateway import ProviderDataGateway
 meta=l.DataLicenceMetadata('feed','terms',l.AcquisitionPermission.ALLOWED,(l.DataUse.RESEARCH,),False,l.ExternalProcessingPermission.ALLOWED)
 ev=DataProvenanceEvidence('prov:1',meta,NOW-timedelta(minutes=1),NOW+timedelta(hours=1),False)
 policy=ProviderDataPolicy('data/v1','cloud-a','1.0.0',(DataClass.MARKET_RESEARCH,))
 return ProviderDataGateway(licence_policy=l.DataLicencePolicy(),audit_sink=(events if events is not None else []).append,clock=lambda:NOW).prepare(raw_request(payload),provider=manifest(),policy=policy,provenance=(ev,))

def test_raw_unclassified_request_cannot_be_dispatched():
 from engine.ai.v2.adapters.cloud import CloudProviderAdapter,ProviderAdapterError
 a=CloudProviderAdapter(manifest(),lambda r:{})
 with pytest.raises(ProviderAdapterError): a.generate(raw_request())

def test_gateway_denial_means_transport_never_called():
 from engine.ai.v2.data_policy import DataProvenanceEvidence,ProviderDataPolicy
 from engine.ai.v2.provider_gateway import ProviderDataGateway,ProviderGatewayDenied
 calls=[]
 meta=l.DataLicenceMetadata('feed','terms',l.AcquisitionPermission.ALLOWED,(l.DataUse.RESEARCH,),False,l.ExternalProcessingPermission.PROHIBITED)
 ev=DataProvenanceEvidence('p',meta,NOW-timedelta(minutes=1),NOW+timedelta(hours=1),False)
 policy=ProviderDataPolicy('data/v1','cloud-a','1.0.0',(DataClass.MARKET_RESEARCH,))
 with pytest.raises(ProviderGatewayDenied): ProviderDataGateway(licence_policy=l.DataLicencePolicy(),audit_sink=lambda e:None,clock=lambda:NOW).prepare(raw_request(),provider=manifest(),policy=policy,provenance=(ev,))
 assert calls==[]

def test_gateway_approved_request_dispatches_once_and_is_structured():
 from engine.ai.v2.adapters.cloud import CloudProviderAdapter
 calls=[]
 def transport(r): calls.append(r); return {'schema_id':'research/v1','payload':{'action':'HOLD'},'provenance_refs':('cloud:out',)}
 out=CloudProviderAdapter(manifest(),transport).generate(ready())
 assert len(calls)==1 and out.provider_id=='cloud-a' and out.schema_id=='research/v1'

def test_timeout_and_malformed_output_fail_closed():
 from engine.ai.v2.adapters.cloud import CloudProviderAdapter,ProviderAdapterUnavailable,ProviderAdapterError
 def timeout(_): raise TimeoutError('slow')
 with pytest.raises(ProviderAdapterUnavailable):CloudProviderAdapter(manifest(),timeout).generate(ready())
 with pytest.raises(ProviderAdapterError):CloudProviderAdapter(manifest(),lambda r:{'schema_id':'wrong','payload':{},'provenance_refs':('p',)}).generate(ready())

def test_gateway_audit_and_ready_metadata_exclude_secret_payloads():
 events=[]; r=ready(events,{'symbol':'NIFTY','api_token':'SECRET-CANARY','nested':{'account_id':'ACC-CANARY','ok':'yes'}})
 assert 'SECRET-CANARY' not in repr(events) and 'ACC-CANARY' not in repr(events)
 assert 'SECRET-CANARY' not in repr(r.sanitized_payload) and 'ACC-CANARY' not in repr(r.sanitized_payload)
 assert r.licensing_fingerprints and r.policy_ref
