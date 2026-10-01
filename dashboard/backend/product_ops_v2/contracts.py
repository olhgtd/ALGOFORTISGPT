"""Phase 9 ProductOps immutable privacy-domain contracts. No trading authority."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

class PrivacyDataClass(str, Enum):
    ACCOUNT_IDENTITY='ACCOUNT_IDENTITY'; DEVICE_SECURITY='DEVICE_SECURITY'; SESSION_SECURITY='SESSION_SECURITY'; ENTITLEMENT='ENTITLEMENT'; CONSENT_EVIDENCE='CONSENT_EVIDENCE'; PRIVACY_REQUEST='PRIVACY_REQUEST'; SUPPORT_METADATA='SUPPORT_METADATA'; NON_SENSITIVE_SETTINGS='NON_SENSITIVE_SETTINGS'; UNKNOWN='UNKNOWN'

class PrivacyOperation(str, Enum):
    STORE='STORE'; READ='READ'; EXPORT='EXPORT'; PROCESSOR_USE='PROCESSOR_USE'; RETAIN='RETAIN'; DELETE='DELETE'; BACKUP='BACKUP'; RESTORE='RESTORE'

@dataclass(frozen=True, slots=True)
class PrivacyPolicy:
    policy_id:str; version:str; data_class:PrivacyDataClass; purpose:str; allowed_operations:tuple[PrivacyOperation,...]; storage_boundary:str; retention_policy_ref:str; processor_scope:tuple[str,...]; transfer_policy_ref:str|None; audit_required:bool; effective_at:datetime; review_at:datetime|None
    def __post_init__(self):
        if not self.policy_id.strip() or not self.version.strip() or not self.purpose.strip(): raise ValueError('policy identity/purpose required')
        if self.data_class is PrivacyDataClass.UNKNOWN: raise ValueError('UNKNOWN cannot be registered as positive policy')
        if self.effective_at.tzinfo is None: raise ValueError('effective_at must be timezone-aware')
        if self.review_at is not None and self.review_at.tzinfo is None: raise ValueError('review_at must be timezone-aware')
        if not self.allowed_operations: raise ValueError('allowed_operations required')

@dataclass(frozen=True, slots=True)
class PrivacyPolicyDecision:
    allowed:bool; reasons:tuple[str,...]; policy_ref:str|None

class ProductOpsRepository(Protocol):
    def append(self, stream:str, record:object)->str: ...
    def list(self, stream:str, principal_ref:str|None=None)->tuple[object,...]: ...

@dataclass(frozen=True, slots=True)
class InMemoryProductOpsRepository:
    """Only a deterministic development repository; not production central storage proof."""
    records:dict[str,list]
    @classmethod
    def create(cls): return cls({})
    def append(self, stream:str, record:object)->str:
        bucket=self.records.setdefault(stream,[]); bucket.append(record); return f'{stream}:{len(bucket)}'
    def list(self, stream:str, principal_ref:str|None=None)->tuple[object,...]:
        values=tuple(self.records.get(stream,()))
        if principal_ref is None: return values
        return tuple(v for v in values if getattr(v,'principal_ref',None)==principal_ref)
