from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class ErasureOutcome(str,Enum): DELETE_ALLOWED='DELETE_ALLOWED'; RETAIN_LEGAL_HOLD='RETAIN_LEGAL_HOLD'; RETAIN_SAFETY='RETAIN_SAFETY'; REJECT_POLICY_UNRESOLVED='REJECT_POLICY_UNRESOLVED'
@dataclass(frozen=True,slots=True)
class RetentionPolicy:
    policy_id:str; version:str; data_class:str; trigger:str; duration_rule_ref:str|None; deletion_action:str; legal_hold_ref:str|None; safety_retention_ref:str|None; backup_propagation:bool
@dataclass(frozen=True,slots=True)
class ErasureDecision:
    outcome:ErasureOutcome; reason_ref:str|None; data_class:str
class ErasureEngine:
    def decide(self, policies:tuple[RetentionPolicy,...], *, now:datetime)->dict[str,ErasureDecision]:
        out={}
        for p in policies:
            if p.legal_hold_ref: decision=ErasureDecision(ErasureOutcome.RETAIN_LEGAL_HOLD,p.legal_hold_ref,p.data_class)
            elif p.safety_retention_ref: decision=ErasureDecision(ErasureOutcome.RETAIN_SAFETY,p.safety_retention_ref,p.data_class)
            elif not p.policy_id or not p.version: decision=ErasureDecision(ErasureOutcome.REJECT_POLICY_UNRESOLVED,None,p.data_class)
            else: decision=ErasureDecision(ErasureOutcome.DELETE_ALLOWED,p.policy_id+'@'+p.version,p.data_class)
            out[p.data_class]=decision
        return out
@dataclass(frozen=True,slots=True)
class MinimalTombstone:
    principal_fingerprint:str; data_class:str; deletion_policy_ref:str; completed_at:datetime
    def __post_init__(self):
        if len(self.principal_fingerprint)!=64: raise ValueError('minimal principal fingerprint required')
