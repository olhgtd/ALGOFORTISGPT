from datetime import datetime,timezone
import pytest
from engine.ai.v2.contracts import DataClass, ProviderHealth, ProviderKind, ProviderManifest, ProviderUsage

def pm(pid,kind,schemas=('research/v1',)):
 return ProviderManifest(pid,kind,'1.0.0','m',schemas,('MARKET_RESEARCH',),None if kind is ProviderKind.LOCAL else 'retention:ok',True)
def binding(pid,kind):
 from engine.ai.v2.providers import ProviderBinding
 return ProviderBinding(pid,'1.0.0',pm(pid,kind))
def pol(pid,fallback=()):
 from engine.ai.v2.routing import ProviderRuntimePolicy
 return ProviderRuntimePolicy(pid,10,2,5000,fallback)
def snap(healthy=True,requests=0,concurrent=0):
 from engine.ai.v2.routing import ProviderRuntimeSnapshot
 return ProviderRuntimeSnapshot(ProviderHealth(healthy,'health',datetime(2026,9,27,tzinfo=timezone.utc)),ProviderUsage(requests,concurrent,'usage'))

def test_router_requires_exactly_configured_local_and_cloud_routes():
 from engine.ai.v2.routing import ProviderRouter, ProviderRoutingError
 with pytest.raises(ProviderRoutingError): ProviderRouter((binding('local',ProviderKind.LOCAL),),local_provider_id='local',cloud_provider_id='cloud',policies=(pol('local'),))

def test_health_quota_and_concurrency_fail_closed_without_fallback():
 from engine.ai.v2.routing import ProviderRouter, ProviderUnavailable
 r=ProviderRouter((binding('local',ProviderKind.LOCAL),binding('cloud',ProviderKind.CLOUD)),local_provider_id='local',cloud_provider_id='cloud',policies=(pol('local'),pol('cloud')))
 for s in (snap(False),snap(True,10,0),snap(True,0,2)):
  with pytest.raises(ProviderUnavailable): r.select('local',schema_id='research/v1',data_classes=(DataClass.MARKET_RESEARCH,),snapshots={'local':s,'cloud':snap()})

def test_only_explicit_compatible_fallback_is_used():
 from engine.ai.v2.routing import ProviderRouter, ProviderUnavailable
 r=ProviderRouter((binding('local',ProviderKind.LOCAL),binding('cloud',ProviderKind.CLOUD)),local_provider_id='local',cloud_provider_id='cloud',policies=(pol('local',('cloud',)),pol('cloud')))
 assert r.select('local',schema_id='research/v1',data_classes=(DataClass.MARKET_RESEARCH,),snapshots={'local':snap(False),'cloud':snap()}).provider_manifest.provider_id=='cloud'
 r2=ProviderRouter((binding('local',ProviderKind.LOCAL),binding('cloud',ProviderKind.CLOUD)),local_provider_id='local',cloud_provider_id='cloud',policies=(pol('local',('unknown',)),pol('cloud')))
 with pytest.raises(ProviderUnavailable):r2.select('local',schema_id='research/v1',data_classes=(DataClass.MARKET_RESEARCH,),snapshots={'local':snap(False),'cloud':snap()})

def test_fallback_must_support_same_schema_and_data_class():
 from engine.ai.v2.routing import ProviderRouter, ProviderUnavailable, ProviderRuntimePolicy
 from engine.ai.v2.providers import ProviderBinding
 bad=ProviderBinding('cloud','1.0.0',pm('cloud',ProviderKind.CLOUD,('other/v1',)))
 r=ProviderRouter((binding('local',ProviderKind.LOCAL),bad),local_provider_id='local',cloud_provider_id='cloud',policies=(pol('local',('cloud',)),pol('cloud')))
 with pytest.raises(ProviderUnavailable):r.select('local',schema_id='research/v1',data_classes=(DataClass.MARKET_RESEARCH,),snapshots={'local':snap(False),'cloud':snap()})
