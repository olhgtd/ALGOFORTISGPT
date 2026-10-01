from __future__ import annotations
from dataclasses import dataclass
from engine.ai.v2.contracts import ProviderManifest
from engine.core.adapter_registry import AdapterKind, InternalAdapterRegistry

class ProviderBindingError(ValueError): pass

@dataclass(frozen=True,slots=True)
class ProviderBinding:
    adapter_id:str
    adapter_version:str
    provider_manifest:ProviderManifest
    def __post_init__(self):
        if not isinstance(self.adapter_id,str) or not self.adapter_id.strip(): raise ProviderBindingError('adapter_id required')
        if not isinstance(self.adapter_version,str) or not self.adapter_version.strip(): raise ProviderBindingError('adapter_version required')
        if not isinstance(self.provider_manifest,ProviderManifest): raise ProviderBindingError('provider_manifest required')
        if self.adapter_id != self.provider_manifest.provider_id: raise ProviderBindingError('adapter/provider id mismatch')

def activate_ai_provider(registry:InternalAdapterRegistry,binding:ProviderBinding):
    if not isinstance(registry,InternalAdapterRegistry) or not isinstance(binding,ProviderBinding): raise ProviderBindingError('invalid binding input')
    matches=[m for m in registry.discover() if m.adapter_id==binding.adapter_id and m.version==binding.adapter_version]
    if len(matches)!=1: raise ProviderBindingError('exact adapter registration required')
    manifest=matches[0]
    if manifest.kind is not AdapterKind.AI_PROVIDER: raise ProviderBindingError('adapter must be AI_PROVIDER')
    if manifest.contract != 'AIProvider@1': raise ProviderBindingError('adapter must implement AIProvider@1')
    return registry.enable(binding.adapter_id,binding.adapter_version)
