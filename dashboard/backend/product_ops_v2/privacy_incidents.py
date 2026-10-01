from __future__ import annotations
from datetime import datetime
from engine.paper.contracts_v2 import FailureIncident, FailureSeverity, PaperOperationalState

class PrivacyIncidentBridge:
    """Adapter onto the existing FailureIncident + injected existing dispatcher."""
    def __init__(self, alert_dispatcher): self._dispatcher=alert_dispatcher
    def raise_incident(self, incident_id:str, *, affected_classes:tuple[str,...], detected_at:datetime, audit_ref:str)->FailureIncident:
        if not audit_ref: raise ValueError('audit evidence required')
        safe_scope=','.join(sorted(set(affected_classes))) or 'PRIVACY_SCOPE_UNSPECIFIED'
        forbidden=('token','secret','password','credential','raw_trade','account_number')
        if any(any(x in item.lower() for x in forbidden) for item in affected_classes): raise ValueError('sensitive incident payload rejected')
        incident=FailureIncident(incident_id=incident_id,failure_type='PRIVACY_BREACH',severity=FailureSeverity.WARNING,detected_at=detected_at,source='PHASE9_PRODUCT_OPS',affected_scope=safe_scope,previous_state=PaperOperationalState.HEALTHY,resulting_state=PaperOperationalState.HEALTHY,transition_reason='PRIVACY_INCIDENT_LOCAL_TRADING_SAFETY_UNCHANGED',halt_latched=False,recovery_id=None,storm_policy_ref=None,resolved_at=None,resolution_evidence=None)
        self._dispatcher.dispatch(incident, f'Privacy incident {incident_id}; classes={safe_scope}; audit={audit_ref}')
        return incident
