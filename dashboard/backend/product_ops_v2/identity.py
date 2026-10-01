from dashboard.backend.account_v2.contracts import DeviceSessionGateStatus
class S2IdentityAuthorizer:
    def __init__(self, gate): self._gate=gate
    def authorize(self, user_id, device_id, session_family_id, now):
        result=self._gate.evaluate(user_id,device_id,session_family_id,now)
        return result.status is DeviceSessionGateStatus.VALID, result
