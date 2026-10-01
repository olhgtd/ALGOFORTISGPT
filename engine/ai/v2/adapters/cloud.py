from __future__ import annotations
from collections.abc import Mapping
from engine.ai.v2.contracts import AIResponse, ProviderKind, ProviderManifest
from engine.ai.v2.provider_gateway import ProviderReadyRequest
from engine.reproducibility.codec import CanonicalCodec

class ProviderAdapterError(ValueError): pass
class ProviderAdapterUnavailable(RuntimeError): pass

def _canonical(v):
    if isinstance(v,Mapping): return tuple((str(k),_canonical(v[k])) for k in sorted(v,key=lambda x:str(x)))
    if isinstance(v,(tuple,list)): return tuple(_canonical(x) for x in v)
    if v is None or isinstance(v,(bool,int,str,bytes)): return v
    return repr(v)

class CloudProviderAdapter:
    def __init__(self,manifest:ProviderManifest,transport):
        if not isinstance(manifest,ProviderManifest) or manifest.kind is not ProviderKind.CLOUD: raise ProviderAdapterError('cloud provider manifest required')
        if not callable(transport): raise ProviderAdapterError('cloud transport callable required')
        self.manifest=manifest; self._transport=transport
    def generate(self,ready:ProviderReadyRequest)->AIResponse:
        if not isinstance(ready,ProviderReadyRequest): raise ProviderAdapterError('gateway-approved ProviderReadyRequest required')
        if ready.provider_id != self.manifest.provider_id or ready.schema_id not in self.manifest.supported_schemas: raise ProviderAdapterError('provider/schema mismatch')
        if not ready.licensing_fingerprints or not ready.policy_ref or not ready.provenance_refs: raise ProviderAdapterError('licensing/policy/provenance evidence required')
        try: raw=self._transport(ready)
        except Exception as exc: raise ProviderAdapterUnavailable('cloud provider unavailable') from exc
        if not isinstance(raw,Mapping): raise ProviderAdapterError('structured provider output required')
        schema=raw.get('schema_id'); payload=raw.get('payload'); refs=raw.get('provenance_refs')
        if schema != ready.schema_id or not isinstance(refs,tuple) or not refs or any(not isinstance(x,str) or not x.strip() for x in refs): raise ProviderAdapterError('malformed provider output')
        fp=CanonicalCodec.fingerprint('algofortis-ai-cloud-response/v1',(("request_id",ready.request_id),("provider_id",self.manifest.provider_id),("model_id",self.manifest.model_id),("schema_id",schema),("gateway_fingerprint",ready.outbound_fingerprint),("payload",_canonical(payload)),("provenance_refs",refs)))
        return AIResponse(ready.request_id,self.manifest.provider_id,self.manifest.model_id,schema,payload,refs,fp)
