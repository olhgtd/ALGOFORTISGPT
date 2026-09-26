from __future__ import annotations

from build.tools.check_s2_account_gate import check


def test_s2_static_qualification_guard_is_clean() -> None:
    assert check() == []
