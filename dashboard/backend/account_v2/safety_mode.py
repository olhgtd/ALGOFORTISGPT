"""Map S2 account-authority results to local runtime safety modes."""
from __future__ import annotations

from .contracts import AccountRuntimeMode, DeviceSessionGateResult, DeviceSessionGateStatus


class AccountSafetyModeMapper:
    @staticmethod
    def map(result: DeviceSessionGateResult) -> AccountRuntimeMode:
        if result.status is DeviceSessionGateStatus.AUTHORITY_UNAVAILABLE:
            return AccountRuntimeMode.LOCAL_SAFETY_ONLY
        return AccountRuntimeMode.NORMAL
