from __future__ import annotations
from collections.abc import Mapping
from engine.ai.v2.contracts import AIRequest, AIResponse, ProviderKind, ProviderManifest
from engine.reproducibility.codec import CanonicalCodec

class ProviderAdapterError(ValueError): pass
class ProviderAdapterUnavailable(RuntimeError): pass

def _canonical(v):
    if isinstance(v,Mapping): return tuple((str(k),_canonical(v[k])) for k in sorted(v,key=lambda x:str(x)))
    if isinstance(v,(tuple,list)): return tuple(_canonical(x) for x in v)
    if v is None or isinstance(v,(bool,int,str,bytes)): return v
    return repr(v)

class LocalProviderAdapter:
    def __init__(self,manifest:ProviderManifest,transport):
        if not isinstance(manifest,ProviderManifest) or manifest.kind is not ProviderKind.LOCAL: raise ProviderAdapterError('local provider manifest required')
        if not callable(transport): raise ProviderAdapterError('local transport callable required')
        self.manifest=manifest; self._transport=transport
    def generate(self,request:AIRequest)->AIResponse:
        if not isinstance(request,AIRequest) or request.schema_id not in self.manifest.supported_schemas: raise ProviderAdapterError('unsupported request')
        try: raw=self._transport(request)
        except Exception as exc: raise ProviderAdapterUnavailable('local provider unavailable') from exc
        if not isinstance(raw,Mapping): raise ProviderAdapterError('structured provider output required')
        schema=raw.get('schema_id'); payload=raw.get('payload'); refs=raw.get('provenance_refs')
        if schema != request.schema_id or not isinstance(refs,tuple) or not refs or any(not isinstance(x,str) or not x.strip() for x in refs): raise ProviderAdapterError('malformed provider output')
        fp=CanonicalCodec.fingerprint('algofortis-ai-local-response/v1',(("request_id",request.request_id),("provider_id",self.manifest.provider_id),("model_id",self.manifest.model_id),("schema_id",schema),("payload",_canonical(payload)),("provenance_refs",refs)))
        return AIResponse(request.request_id,self.manifest.provider_id,self.manifest.model_id,schema,payload,refs,fp)
