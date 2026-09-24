from build.tools.phase4_probe import run


def test_probe_is_reproducible():
    assert run() == run()


def test_probe_emits_fail_closed_promotion_bundle():
    from build.tools.phase4_probe import promotion_probe
    fingerprint, status = promotion_probe()
    assert len(fingerprint) == 64
    assert status == "NON_PROMOTABLE"


def test_probe_includes_policy_bound_orb_options_run():
    from build.tools.phase4_probe import orb_option_probe
    assert orb_option_probe() == orb_option_probe()
