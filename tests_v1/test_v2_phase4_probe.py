from build.tools.phase4_probe import run


def test_probe_is_reproducible():
    assert run() == run()


def test_probe_emits_fail_closed_promotion_bundle():
    from build.tools.phase4_probe import promotion_probe
    fingerprint, status = promotion_probe()
    assert len(fingerprint) == 64
    assert status == "NON_PROMOTABLE"
