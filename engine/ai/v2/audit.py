"""Safe Phase-8 AI audit evidence and fail-closed provider dispatch coordination."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import re


class AIAuditError(RuntimeError):
    pass


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AIAuditError(f"{name} must be non-empty string")
    return value.strip()


def _aware(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AIAuditError(f"{name} must be timezone-aware datetime")
    return value


def _fp(value: object, name: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    text = _text(value, name).lower()
    if _HEX64.fullmatch(text) is None:
        raise AIAuditError(f"{name} must be lowercase sha256 hex")
    return text


@dataclass(frozen=True, slots=True)
class AIAuditEvent:
    event_id: str
    action: str
    correlation_id: str
    sequence: int
    provider_id: str
    model_id: str
    tool_id: str | None
    policy_ref: str
    licensing_ref: str
    input_fingerprint: str
    output_fingerprint: str | None
    status: str
    occurred_at: datetime

    @classmethod
    def create(cls, *, action: str, correlation_id: str, sequence: int, provider_id: str, model_id: str,
               tool_id: str | None, policy_ref: str, licensing_ref: str, input_fingerprint: str,
               output_fingerprint: str | None, status: str, occurred_at: datetime) -> "AIAuditEvent":
        action=_text(action,'action'); correlation_id=_text(correlation_id,'correlation_id')
        provider_id=_text(provider_id,'provider_id'); model_id=_text(model_id,'model_id')
        if tool_id is not None: tool_id=_text(tool_id,'tool_id')
        policy_ref=_text(policy_ref,'policy_ref'); licensing_ref=_text(licensing_ref,'licensing_ref')
        input_fingerprint=_fp(input_fingerprint,'input_fingerprint')  # type: ignore[assignment]
        output_fingerprint=_fp(output_fingerprint,'output_fingerprint',optional=True)
        status=_text(status,'status'); occurred_at=_aware(occurred_at,'occurred_at')
        if isinstance(sequence,bool) or not isinstance(sequence,int) or sequence < 1:
            raise AIAuditError('sequence must be positive integer')
        payload='|'.join((action,correlation_id,str(sequence),provider_id,model_id,tool_id or '',policy_ref,licensing_ref,input_fingerprint or '',output_fingerprint or '',status,occurred_at.astimezone(timezone.utc).isoformat()))
        event_id=hashlib.sha256(payload.encode('utf-8')).hexdigest()
        return cls(event_id,action,correlation_id,sequence,provider_id,model_id,tool_id,policy_ref,licensing_ref,input_fingerprint or '',output_fingerprint,status,occurred_at)


class AuditedAction:
    def __init__(self,audit_sink):
        if not callable(audit_sink): raise AIAuditError('audit_sink must be callable')
        self._audit=audit_sink
    def run(self,event:AIAuditEvent,action):
        if not isinstance(event,AIAuditEvent) or not callable(action): raise AIAuditError('invalid audited action')
        try: self._audit(event)
        except Exception as exc: raise AIAuditError('AI audit failed') from exc
        return action()


class DispatchStatus(str,Enum):
    DISPATCHED='DISPATCHED'
    NO_TRADE='NO_TRADE'

@dataclass(frozen=True,slots=True)
class ProviderDispatchAudit:
    provider_id:str
    status:str='READY_TO_DISPATCH'

@dataclass(frozen=True,slots=True)
class ProviderDispatchResult:
    status:DispatchStatus
    selected_provider_id:str|None
    result:object|None=None
    reason:str|None=None


class FailClosedProviderDispatch:
    """Composes existing router/gateway/invoke seams without bypassing any of them."""
    def __init__(self,*,router,prepare,invoke,audit_sink):
        if not callable(getattr(router,'select',None)) or not callable(prepare) or not callable(invoke) or not callable(audit_sink):
            raise AIAuditError('router/prepare/invoke/audit interfaces are required')
        self._router=router; self._prepare=prepare; self._invoke=invoke; self._audit=audit_sink

    def execute(self,*,provider_id:str,schema_id:str,data_classes:tuple,snapshots:dict)->ProviderDispatchResult:
        try:
            binding=self._router.select(provider_id=provider_id,schema_id=schema_id,data_classes=data_classes,snapshots=snapshots)
            ready=self._prepare(binding)
            selected=_text(binding.provider_manifest.provider_id,'selected_provider_id')
            event=ProviderDispatchAudit(selected)
            try: self._audit(event)
            except Exception as exc: raise AIAuditError('provider dispatch audit failed') from exc
            result=self._invoke(ready)
            return ProviderDispatchResult(DispatchStatus.DISPATCHED,selected,result,None)
        except AIAuditError:
            raise
        except Exception as exc:
            return ProviderDispatchResult(DispatchStatus.NO_TRADE,None,None,str(exc))


__all__=['AIAuditError','AIAuditEvent','AuditedAction','DispatchStatus','ProviderDispatchAudit','ProviderDispatchResult','FailClosedProviderDispatch']
