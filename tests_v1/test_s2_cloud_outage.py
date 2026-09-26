from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from dashboard.backend.account_v2.contracts import AccountRuntimeMode, DeviceSessionGateStatus
from dashboard.backend.account_v2.gate import DeviceSessionGate
from dashboard.backend.account_v2.safety_mode import AccountSafetyModeMapper


class _UnavailableRepository:
    def get_device(self, **_kwargs):
        raise TimeoutError("central account authority unavailable")


def test_authority_timeout_maps_to_local_safety_only_without_arm_authority() -> None:
    result = DeviceSessionGate(_UnavailableRepository()).evaluate(
        uuid4(),
        "dev-1",
        "fam-1",
        datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc),
    )

    assert result.status is DeviceSessionGateStatus.AUTHORITY_UNAVAILABLE
    assert AccountSafetyModeMapper.map(result) is AccountRuntimeMode.LOCAL_SAFETY_ONLY
    assert not ({"arm", "place_order", "cancel_order", "modify_order"} & set(dir(result)))
