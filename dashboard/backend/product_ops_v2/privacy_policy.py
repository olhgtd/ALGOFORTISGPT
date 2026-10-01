from __future__ import annotations
from datetime import datetime
from .contracts import PrivacyDataClass, PrivacyOperation, PrivacyPolicy, PrivacyPolicyDecision

class PrivacyPolicyError(ValueError): pass

class PrivacyPolicyRegistry:
    def __init__(self, policies:tuple[PrivacyPolicy,...]=()):
        self._policies={}
        for p in policies:
            key=(p.data_class,p.policy_id,p.version)
            if key in self._policies: raise PrivacyPolicyError('duplicate privacy policy')
            self._policies[key]=p
    def resolve(self, data_class:PrivacyDataClass, operation:PrivacyOperation, now:datetime, *, purpose:str|None=None, processor:str|None=None, transfer_evidence_ref:str|None=None)->PrivacyPolicyDecision:
        if data_class is PrivacyDataClass.UNKNOWN: return PrivacyPolicyDecision(False,('UNKNOWN_DATA_CLASS',),None)
        candidates=[p for p in self._policies.values() if p.data_class is data_class and (purpose is None or p.purpose==purpose) and p.effective_at<=now and (p.review_at is None or now<=p.review_at)]
        if not candidates: return PrivacyPolicyDecision(False,('MISSING_OR_STALE_POLICY',),None)
        if len(candidates)!=1: return PrivacyPolicyDecision(False,('AMBIGUOUS_POLICY',),None)
        p=candidates[0]; reasons=[]
        if operation not in p.allowed_operations: reasons.append('OPERATION_NOT_PERMITTED')
        if processor is not None and processor not in p.processor_scope: reasons.append('PROCESSOR_NOT_PERMITTED')
        if operation in (PrivacyOperation.EXPORT,PrivacyOperation.PROCESSOR_USE) and p.transfer_policy_ref and not transfer_evidence_ref: reasons.append('TRANSFER_EVIDENCE_MISSING')
        return PrivacyPolicyDecision(not reasons,tuple(reasons),f'{p.policy_id}@{p.version}')
