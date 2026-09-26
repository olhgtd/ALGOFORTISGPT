from build.tools.phase4_probe import run


def test_probe_is_reproducible():
    assert run() == run()


def test_probe_emits_fail_closed_promotion_bundle():
    from build.tools.phase4_probe import promotion_probe
    fingerprint, status = promotion_probe()
    assert len(fingerprint) == 64
    assert status == "NON_PROMOTABLE"


def test_test_only_bundle_is_structured_and_cannot_promote():
    from engine.strategy.promotion_v2 import PromotionAttemptBundle
    from engine.data.licensing import AcquisitionPermission, DataLicenceMetadata, DataLicencePolicy, DataUse
    decision = DataLicencePolicy().evaluate(DataLicenceMetadata(
        "fixture", "fixture@v1", AcquisitionPermission.ALLOWED, (DataUse.PROMOTION,), synthetic=True),
        market="NSE", requested_use=DataUse.PROMOTION, programmatic_acquisition=False)
    bundle = PromotionAttemptBundle.test_only(validation_fingerprint="a" * 64,
        overfitting_fingerprint="b" * 64, licence=decision)
    assert bundle.status == "NON_PROMOTABLE"
    assert "SYNTHETIC_NOT_PROMOTION_EVIDENCE" in bundle.reasons


def test_probe_includes_policy_bound_orb_options_run():
    from build.tools.phase4_probe import orb_option_probe
    assert orb_option_probe() == orb_option_probe()
