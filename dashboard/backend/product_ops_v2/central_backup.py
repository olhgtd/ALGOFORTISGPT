from dataclasses import dataclass
@dataclass(frozen=True,slots=True)
class CentralBackupRecord: data_class:str; evidence_ref:str
@dataclass(frozen=True,slots=True)
class CentralBackupDecision: allowed:bool; reasons:tuple[str,...]
class CentralPrivacyBackupService:
    FORBIDDEN={'BROKER_CREDENTIAL','DEVICE_PRIVATE_KEY','STRATEGY_CONTENT','LIVE_POSITION','BALANCE','RAW_TRADE_LOG','LOCAL_TRADING_STATE'}
    def __init__(self, *, allowed_classes:set[str]): self._allowed=set(allowed_classes)
    def validate(self, records:tuple[CentralBackupRecord,...])->CentralBackupDecision:
        reasons=[]
        for r in records:
            if r.data_class in self.FORBIDDEN: reasons.append('LOCAL_OR_SECRET_CLASS_FORBIDDEN:'+r.data_class)
            elif r.data_class not in self._allowed: reasons.append('UNAPPROVED_CENTRAL_CLASS:'+r.data_class)
            if not r.evidence_ref: reasons.append('EVIDENCE_REF_MISSING:'+r.data_class)
        return CentralBackupDecision(not reasons,tuple(sorted(set(reasons))))
