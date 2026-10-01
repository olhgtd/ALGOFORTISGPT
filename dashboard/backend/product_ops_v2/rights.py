from __future__ import annotations
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from uuid import UUID
from dashboard.backend.account_v2.contracts import DeviceSessionGateStatus

class RightsRequestType(str,Enum): ACCESS='ACCESS'; CORRECTION_UPDATE='CORRECTION_UPDATE'; ERASURE='ERASURE'; GRIEVANCE='GRIEVANCE'; NOMINATION='NOMINATION'
class RightsState(str,Enum): RECEIVED='RECEIVED'; IDENTITY_CHECK='IDENTITY_CHECK'; ACCEPTED='ACCEPTED'; REJECTED='REJECTED'; IN_PROGRESS='IN_PROGRESS'; COMPLETED='COMPLETED'
@dataclass(frozen=True,slots=True)
class RightsRequest:
    request_id:str; principal_user_id:UUID; request_type:RightsRequestType; state:RightsState; created_at:datetime; identity_authority:str|None=None; reason:str|None=None
class RightsWorkflow:
    def __init__(self, s2_gate): self._gate=s2_gate
    def receive(self, *, request_id:str, principal_user_id:UUID, requested_user_id:UUID, request_type:RightsRequestType, now:datetime)->RightsRequest:
        if requested_user_id!=principal_user_id: raise ValueError('CROSS_USER_REQUEST_DENIED')
        return RightsRequest(request_id,principal_user_id,request_type,RightsState.IDENTITY_CHECK,now)
    def identity_check(self, request:RightsRequest, *, device_id:str, session_family_id:str|None, now:datetime)->RightsRequest:
        if request.state is not RightsState.IDENTITY_CHECK: raise ValueError('INVALID_RIGHTS_TRANSITION')
        result=self._gate.evaluate(request.principal_user_id,device_id,session_family_id,now)
        if result.status is DeviceSessionGateStatus.VALID:
            return replace(request,state=RightsState.ACCEPTED,identity_authority='S2_DEVICE_SESSION_GATE',reason=result.reasons[0] if result.reasons else None)
        return replace(request,state=RightsState.REJECTED,identity_authority='S2_DEVICE_SESSION_GATE',reason=result.status.value)
    def start(self, request:RightsRequest)->RightsRequest:
        if request.state is not RightsState.ACCEPTED: raise ValueError('INVALID_RIGHTS_TRANSITION')
        return replace(request,state=RightsState.IN_PROGRESS)
    def complete(self, request:RightsRequest)->RightsRequest:
        if request.state is not RightsState.IN_PROGRESS: raise ValueError('INVALID_RIGHTS_TRANSITION')
        return replace(request,state=RightsState.COMPLETED)
