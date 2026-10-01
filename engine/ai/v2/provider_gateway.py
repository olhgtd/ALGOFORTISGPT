from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Mapping
from engine.ai.v2.contracts import AIRequest, DataClass, ProviderKind, ProviderManifest
from engine.ai.v2.data_policy import DataProvenanceEvidence, ProviderDataPolicy
from engine.data.licensing import DataLicencePolicy, DataUse
from engine.reproducibility.codec import CanonicalCodec

class ProviderGatewayDenied(RuntimeError): pass

_FORBIDDEN_CLASSES=frozenset({DataClass.BROKER_CREDENTIAL,DataClass.BROKER_ACCOUNT_IDENTIFIER,DataClass.PERSONAL_DATA,DataClass.RAW_TRADE_LOG,DataClass.PRIVATE_KEY,DataClass.UNKNOWN})
_SENSITIVE_KEY_PARTS=('password','passwd','secret','token','api_key','apikey','account_id','accountid','broker_id','brokerid','private_key','privatekey','raw_trade_log')

@dataclass(frozen=True,slots=True)
class ProviderGatewayAuditEvent:
    request_id:str
    provider_id:str
    policy_ref:str
    data_classes:tuple[str,...]
    provenance_refs:tuple[str,...]
    licensing_fingerprints:tuple[str,...]
    outbound_fingerprint:str

@dataclass(frozen=True,slots=True)
class ProviderReadyRequest:
    request_id:str
    provider_id:str
    schema_id:str
    sanitized_payload:object
    policy_ref:str
    provenance_refs:tuple[str,...]
    licensing_fingerprints:tuple[str,...]
    outbound_fingerprint:str


def _safe_value(value:object)->object:
    if isinstance(value,Mapping):
        out=[]
        for key in sorted(value,key=lambda x:str(x)):
            k=str(key); normalized=k.lower().replace('-','_').replace(' ','_')
            if any(part in normalized for part in _SENSITIVE_KEY_PARTS): continue
            out.append((k,_safe_value(value[key])))
        return tuple(out)
    if isinstance(value,(tuple,list)): return tuple(_safe_value(v) for v in value)
    if value is None or isinstance(value,(bool,int,str,bytes)): return value
    return repr(value)

def _restore(value:object)->object:
    if isinstance(value,tuple) and all(isinstance(x,tuple) and len(x)==2 and isinstance(x[0],str) for x in value): return {k:_restore(v) for k,v in value}
    if isinstance(value,tuple): return tuple(_restore(v) for v in value)
    return value

class ProviderDataGateway:
    def __init__(self,*,licence_policy:DataLicencePolicy,audit_sink:Callable[[ProviderGatewayAuditEvent],None],clock:Callable[[],datetime]):
        if not isinstance(licence_policy,DataLicencePolicy): raise TypeError('licence_policy must be DataLicencePolicy')
        if not callable(audit_sink) or not callable(clock): raise TypeError('audit_sink and clock must be callable')
        self._licence_policy=licence_policy; self._audit_sink=audit_sink; self._clock=clock

    def prepare(self,request:AIRequest,*,provider:ProviderManifest,policy:ProviderDataPolicy,provenance:tuple[DataProvenanceEvidence,...])->ProviderReadyRequest:
        if not isinstance(request,AIRequest) or not isinstance(provider,ProviderManifest) or not isinstance(policy,ProviderDataPolicy): raise ProviderGatewayDenied('invalid gateway input')
        if provider.provider_id != policy.provider_id: raise ProviderGatewayDenied('provider policy mismatch')
        if request.schema_id not in provider.supported_schemas: raise ProviderGatewayDenied('schema not supported by provider')
        if any(cls in _FORBIDDEN_CLASSES for cls in request.data_classes): raise ProviderGatewayDenied('forbidden or unknown data class')
        if any(cls not in policy.allowed_data_classes for cls in request.data_classes): raise ProviderGatewayDenied('data class not allowed by policy')
        if any(cls.value not in provider.accepted_data_classes for cls in request.data_classes): raise ProviderGatewayDenied('data class not accepted by provider manifest')
        now=self._clock()
        if now.tzinfo is None or now.utcoffset() is None: raise ProviderGatewayDenied('clock must be timezone-aware')
        if not provenance: raise ProviderGatewayDenied('provenance evidence required')
        licensing=[]; prov_refs=[]
        for ev in provenance:
            if not isinstance(ev,DataProvenanceEvidence) or ev.ambiguous or now >= ev.valid_until: raise ProviderGatewayDenied('missing stale or ambiguous provenance evidence')
            legacy=self._licence_policy.evaluate(ev.metadata,market='LOCAL',requested_use=DataUse.RESEARCH,programmatic_acquisition=False)
            if not legacy.allowed: raise ProviderGatewayDenied('dataset use policy denied')
            if provider.kind is ProviderKind.CLOUD:
                ext=self._licence_policy.evaluate_external_processing(ev.metadata,requested_use=DataUse.RESEARCH)
                if not ext.allowed: raise ProviderGatewayDenied('external processing licensing denied')
                licensing.append(ext.fingerprint)
            else:
                licensing.append(legacy.fingerprint)
            prov_refs.append(ev.evidence_ref)
        sanitized_canonical=_safe_value(request.payload)
        outbound_fp=CanonicalCodec.fingerprint('algofortis-ai-provider-ready/v1',(("request_id",request.request_id),("provider_id",provider.provider_id),("schema_id",request.schema_id),("data_classes",tuple(c.value for c in request.data_classes)),("policy_ref",f"{policy.policy_id}@{policy.version}"),("provenance_refs",tuple(prov_refs)),("licensing_fingerprints",tuple(licensing)),("sanitized_payload",sanitized_canonical)))
        event=ProviderGatewayAuditEvent(request.request_id,provider.provider_id,f"{policy.policy_id}@{policy.version}",tuple(c.value for c in request.data_classes),tuple(prov_refs),tuple(licensing),outbound_fp)
        try: self._audit_sink(event)
        except Exception as exc: raise ProviderGatewayDenied('provider gateway audit failed') from exc
        return ProviderReadyRequest(request.request_id,provider.provider_id,request.schema_id,_restore(sanitized_canonical),event.policy_ref,event.provenance_refs,event.licensing_fingerprints,outbound_fp)
