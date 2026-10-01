import pytest
from engine.ai.v2.contracts import AIRequest, DataClass, ProviderKind, ProviderManifest

def manifest(): return ProviderManifest('local-a',ProviderKind.LOCAL,'1.0.0','model-a',('research/v1',),('MARKET_RESEARCH',),None,False)
def request(): return AIRequest('r1','research/v1',(DataClass.MARKET_RESEARCH,),{'symbol':'NIFTY'},('prov:1',))

def test_missing_transport_fails_closed():
 from engine.ai.v2.adapters.local import LocalProviderAdapter, ProviderAdapterError
 with pytest.raises(ProviderAdapterError): LocalProviderAdapter(manifest(),None)

def test_malformed_or_wrong_schema_output_is_rejected():
 from engine.ai.v2.adapters.local import LocalProviderAdapter, ProviderAdapterError
 with pytest.raises(ProviderAdapterError): LocalProviderAdapter(manifest(),lambda r:{'bad':1}).generate(request())
 with pytest.raises(ProviderAdapterError): LocalProviderAdapter(manifest(),lambda r:{'schema_id':'other/v1','payload':{},'provenance_refs':('p',)}).generate(request())

def test_timeout_or_transport_error_becomes_unavailable():
 from engine.ai.v2.adapters.local import LocalProviderAdapter, ProviderAdapterUnavailable
 def timeout(_): raise TimeoutError('slow')
 with pytest.raises(ProviderAdapterUnavailable): LocalProviderAdapter(manifest(),timeout).generate(request())

def test_structured_response_and_fingerprint_are_deterministic():
 from engine.ai.v2.adapters.local import LocalProviderAdapter
 transport=lambda r:{'schema_id':'research/v1','payload':{'action':'HOLD','score':1},'provenance_refs':('model:local',)}
 a=LocalProviderAdapter(manifest(),transport).generate(request()); b=LocalProviderAdapter(manifest(),transport).generate(request())
 assert a.schema_id=='research/v1' and a.provider_id=='local-a' and a.model_id=='model-a'
 assert a.output_fingerprint==b.output_fingerprint
