from __future__ import annotations
from dataclasses import dataclass
from engine.ai.v2.contracts import DataClass, ProviderHealth, ProviderKind, ProviderUsage
from engine.ai.v2.providers import ProviderBinding

class ProviderRoutingError(ValueError): pass
class ProviderUnavailable(RuntimeError): pass

@dataclass(frozen=True,slots=True)
class ProviderRuntimePolicy:
    provider_id:str
    max_requests:int
    max_concurrency:int
    timeout_ms:int
    approved_fallbacks:tuple[str,...]=()
    def __post_init__(self):
        if not isinstance(self.provider_id,str) or not self.provider_id.strip(): raise ProviderRoutingError('provider_id required')
        for n in ('max_requests','max_concurrency','timeout_ms'):
            v=getattr(self,n)
            if isinstance(v,bool) or not isinstance(v,int) or v<=0: raise ProviderRoutingError(f'{n} must be positive integer')
        if not isinstance(self.approved_fallbacks,tuple) or any(not isinstance(x,str) or not x.strip() for x in self.approved_fallbacks): raise ProviderRoutingError('approved_fallbacks must be string tuple')

@dataclass(frozen=True,slots=True)
class ProviderRuntimeSnapshot:
    health:ProviderHealth
    usage:ProviderUsage
    def __post_init__(self):
        if not isinstance(self.health,ProviderHealth) or not isinstance(self.usage,ProviderUsage): raise ProviderRoutingError('invalid runtime snapshot')

class ProviderRouter:
    def __init__(self,bindings:tuple[ProviderBinding,...],*,local_provider_id:str,cloud_provider_id:str,policies:tuple[ProviderRuntimePolicy,...]):
        self._bindings={b.provider_manifest.provider_id:b for b in bindings}
        self._policies={p.provider_id:p for p in policies}
        if len(self._bindings)!=len(bindings) or len(self._policies)!=len(policies): raise ProviderRoutingError('duplicate provider configuration')
        local=self._bindings.get(local_provider_id); cloud=self._bindings.get(cloud_provider_id)
        if local is None or local.provider_manifest.kind is not ProviderKind.LOCAL: raise ProviderRoutingError('exactly one configured local route required')
        if cloud is None or cloud.provider_manifest.kind is not ProviderKind.CLOUD: raise ProviderRoutingError('exactly one configured cloud route required')
        if local_provider_id==cloud_provider_id: raise ProviderRoutingError('local/cloud routes must differ')
        if set(self._bindings)!=set(self._policies): raise ProviderRoutingError('every provider requires runtime policy')
        self.local_provider_id=local_provider_id; self.cloud_provider_id=cloud_provider_id

    def _eligible(self,pid:str,*,schema_id:str,data_classes:tuple[DataClass,...],snapshots:dict[str,ProviderRuntimeSnapshot])->ProviderBinding|None:
        b=self._bindings.get(pid); p=self._policies.get(pid); s=snapshots.get(pid)
        if b is None or p is None or s is None or not s.health.healthy: return None
        if s.usage.request_count >= p.max_requests or s.usage.concurrent_requests >= p.max_concurrency: return None
        m=b.provider_manifest
        if schema_id not in m.supported_schemas: return None
        if any(c.value not in m.accepted_data_classes for c in data_classes): return None
        return b

    def select(self,provider_id:str,*,schema_id:str,data_classes:tuple[DataClass,...],snapshots:dict[str,ProviderRuntimeSnapshot])->ProviderBinding:
        chosen=self._eligible(provider_id,schema_id=schema_id,data_classes=data_classes,snapshots=snapshots)
        if chosen is not None: return chosen
        p=self._policies.get(provider_id)
        if p is None: raise ProviderUnavailable('unknown provider')
        for fallback in p.approved_fallbacks:
            candidate=self._eligible(fallback,schema_id=schema_id,data_classes=data_classes,snapshots=snapshots)
            if candidate is not None: return candidate
        raise ProviderUnavailable('provider unavailable and no approved compatible fallback')
