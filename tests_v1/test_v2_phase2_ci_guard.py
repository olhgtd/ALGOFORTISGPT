from pathlib import Path

from build.tools.check_phase2_safety_spine import check_phase2_safety_spine


def test_phase2_safety_spine_static_contract_is_present_and_clean() -> None:
    assert check_phase2_safety_spine(Path(".")) == ()
