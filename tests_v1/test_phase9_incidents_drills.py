from datetime import datetime, timezone
import pytest

from engine.paper.contracts_v2 import FailureIncident
from dashboard.backend.product_ops_v2.privacy_incidents import PrivacyIncidentBridge
from dashboard.backend.product_ops_v2.central_backup import CentralPrivacyBackupService, CentralBackupRecord
from dashboard.backend.product_ops_v2.drills import DrillResult

NOW=datetime(2026,10,1,tzinfo=timezone.utc)

class Dispatcher:
    def __init__(self): self.calls=[]
    def dispatch(self, incident, message): self.calls.append((incident,message)); return ('alert-email','alert-telegram')

def test_privacy_incident_reuses_failure_incident_and_sanitizes_payload():
    d=Dispatcher(); bridge=PrivacyIncidentBridge(d)
    incident=bridge.raise_incident('p1', affected_classes=('ACCOUNT_IDENTITY',), detected_at=NOW, audit_ref='audit-1')
    assert isinstance(incident, FailureIncident)
    assert incident.failure_type=='PRIVACY_BREACH'
    assert d.calls and 'credential' not in d.calls[0][1].lower()

def test_central_backup_rejects_local_trading_and_secret_classes():
    svc=CentralPrivacyBackupService(allowed_classes={'ACCOUNT_IDENTITY','CONSENT_EVIDENCE','PRIVACY_REQUEST'})
    ok=svc.validate((CentralBackupRecord('ACCOUNT_IDENTITY','ref-1'),))
    assert ok.allowed
    for forbidden in ('BROKER_CREDENTIAL','DEVICE_PRIVATE_KEY','STRATEGY_CONTENT','LIVE_POSITION','BALANCE','RAW_TRADE_LOG'):
        assert not svc.validate((CentralBackupRecord(forbidden,'x'),)).allowed

def test_drill_result_is_deterministic_evidence_contract():
    result=DrillResult.build('RUNBOOK_LOCAL_BACKUP_RESTORE/v1','test',NOW,NOW,(('manifest','PASS'),('isolated_restore','PASS')))
    assert result.passed and len(result.evidence_fingerprint)==64
