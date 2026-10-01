from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from .contracts import PrivacyDataClass

class ConsentAction(str,Enum): ACKNOWLEDGE='ACKNOWLEDGE'; GRANT='GRANT'; WITHDRAW='WITHDRAW'
@dataclass(frozen=True,slots=True)
class ConsentPolicy:
    policy_id:str; version:str; document_fingerprint:str; locale:str; purposes:tuple[str,...]; data_classes:tuple[PrivacyDataClass,...]; effective_at:datetime; withdrawal_policy:str; legal_review_ref:str
    def __post_init__(self):
        if len(self.document_fingerprint)!=64: raise ValueError('document fingerprint required')
        if self.effective_at.tzinfo is None: raise ValueError('effective_at must be timezone-aware')
@dataclass(frozen=True,slots=True)
class ConsentRecord:
    principal_ref:str; policy_id:str; policy_version:str; document_fingerprint:str; action:ConsentAction; acted_at:datetime; audit_ref:str
class ConsentLedger:
    def __init__(self): self._policies={}; self._records=[]
    def record(self, principal_ref:str, policy:ConsentPolicy, action:ConsentAction, acted_at:datetime, *, audit_ref:str)->ConsentRecord:
        if not audit_ref: raise ValueError('audit evidence required')
        key=(policy.policy_id,policy.version); prior=self._policies.get(key)
        if prior is not None and prior!=policy: raise ValueError('immutable consent policy version conflict')
        self._policies[key]=policy
        rec=ConsentRecord(principal_ref,key[0],key[1],policy.document_fingerprint,action,acted_at,audit_ref); self._records.append(rec); return rec
    def history(self, principal_ref:str)->tuple[ConsentRecord,...]: return tuple(r for r in self._records if r.principal_ref==principal_ref)
