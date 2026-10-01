import pytest
from engine.core.adapter_registry import AdapterKind, AdapterManifest, AdapterRegistration, InternalAdapterRegistry, AdapterRegistryError
from engine.ai.v2.contracts import ProviderKind, ProviderManifest

def reg(audit=lambda e:None): return InternalAdapterRegistry(core_version='2.0.0',supported_contracts={'AIProvider':1,'BrokerAdapter':1},audit_sink=audit)
def pm(pid,kind): return ProviderManifest(pid,kind,'1.0.0','m',('research/v1',),('MARKET_RESEARCH',),None if kind is ProviderKind.LOCAL else 'retention:ok',False)
def add(r,aid,kind=AdapterKind.AI_PROVIDER,contract='AIProvider@1'):
 r.register(AdapterRegistration(AdapterManifest(aid,kind,'1.0.0',contract,('generate',),('research',),'>=2.0.0,<3.0.0'),lambda:object()))

def test_non_ai_adapter_and_wrong_contract_cannot_bind():
 from engine.ai.v2.providers import ProviderBinding, activate_ai_provider, ProviderBindingError
 r=reg();add(r,'not-ai',AdapterKind.BROKER,'BrokerAdapter@1')
 with pytest.raises(ProviderBindingError): activate_ai_provider(r,ProviderBinding('not-ai','1.0.0',pm('not-ai',ProviderKind.LOCAL)))
 r2=reg();add(r2,'wrong',AdapterKind.AI_PROVIDER,'BrokerAdapter@1')
 with pytest.raises(ProviderBindingError): activate_ai_provider(r2,ProviderBinding('wrong','1.0.0',pm('wrong',ProviderKind.LOCAL)))

def test_registry_audit_failure_still_prevents_activation():
 from engine.ai.v2.providers import ProviderBinding, activate_ai_provider
 def bad(_): raise RuntimeError('audit')
 r=reg(bad);add(r,'local')
 with pytest.raises(AdapterRegistryError): activate_ai_provider(r,ProviderBinding('local','1.0.0',pm('local',ProviderKind.LOCAL)))
