from __future__ import annotations

from importlib import import_module

import pytest


def _api():
    try:
        return import_module("engine.data.licensing")
    except ModuleNotFoundError:
        pytest.fail("engine.data.licensing is missing", pytrace=False)


def test_missing_or_unknown_acquisition_permission_fails_closed():
    api = _api()
    policy = api.DataLicencePolicy()

    missing = api.DataLicenceMetadata(
        source_id="vendor-a",
        licence_ref="lic-1",
        acquisition_permission=None,
        permitted_uses=(api.DataUse.RESEARCH,),
        synthetic=False,
    )
    unknown = api.DataLicenceMetadata(
        source_id="vendor-a",
        licence_ref="lic-1",
        acquisition_permission=api.AcquisitionPermission.UNKNOWN,
        permitted_uses=(api.DataUse.RESEARCH,),
        synthetic=False,
    )

    assert policy.evaluate(missing, market="BSE", requested_use=api.DataUse.RESEARCH, programmatic_acquisition=True).allowed is False
    assert policy.evaluate(unknown, market="BSE", requested_use=api.DataUse.RESEARCH, programmatic_acquisition=True).allowed is False


def test_explicit_prohibited_acquisition_is_denied():
    api = _api()
    metadata = api.DataLicenceMetadata(
        source_id="vendor-a",
        licence_ref="lic-1",
        acquisition_permission=api.AcquisitionPermission.PROHIBITED,
        permitted_uses=(api.DataUse.RESEARCH,),
        synthetic=False,
    )
    decision = api.DataLicencePolicy().evaluate(
        metadata, market="BSE", requested_use=api.DataUse.RESEARCH, programmatic_acquisition=True
    )
    assert decision.allowed is False
    assert api.DataLicenceReason.ACQUISITION_PROHIBITED in decision.reasons


def test_research_only_data_cannot_be_promoted():
    api = _api()
    metadata = api.DataLicenceMetadata(
        source_id="licensed-vendor",
        licence_ref="terms-v3",
        acquisition_permission=api.AcquisitionPermission.ALLOWED,
        permitted_uses=(api.DataUse.RESEARCH, api.DataUse.BACKTEST),
        synthetic=False,
    )
    decision = api.DataLicencePolicy().evaluate(
        metadata, market="BSE", requested_use=api.DataUse.PROMOTION, programmatic_acquisition=False
    )
    assert decision.allowed is False
    assert api.DataLicenceReason.USE_NOT_PERMITTED in decision.reasons


def test_synthetic_data_is_labelled_and_never_promotion_evidence():
    api = _api()
    metadata = api.DataLicenceMetadata(
        source_id="synthetic-options-model",
        licence_ref="internal-model-v1",
        acquisition_permission=api.AcquisitionPermission.ALLOWED,
        permitted_uses=(api.DataUse.RESEARCH, api.DataUse.BACKTEST, api.DataUse.PROMOTION),
        synthetic=True,
    )

    research = api.DataLicencePolicy().evaluate(
        metadata, market="NSE", requested_use=api.DataUse.RESEARCH, programmatic_acquisition=False
    )
    promotion = api.DataLicencePolicy().evaluate(
        metadata, market="NSE", requested_use=api.DataUse.PROMOTION, programmatic_acquisition=False
    )

    assert research.allowed is True
    assert "SYNTHETIC" in research.labels
    assert promotion.allowed is False
    assert api.DataLicenceReason.SYNTHETIC_NOT_PROMOTION_EVIDENCE in promotion.reasons
    assert "SYNTHETIC" in promotion.labels


def test_nse_programmatic_acquisition_prohibition_cannot_be_overridden_by_metadata():
    api = _api()
    metadata = api.DataLicenceMetadata(
        source_id="claims-fully-licensed",
        licence_ref="terms-v99",
        acquisition_permission=api.AcquisitionPermission.ALLOWED,
        permitted_uses=(api.DataUse.RESEARCH, api.DataUse.BACKTEST),
        synthetic=False,
    )
    decision = api.DataLicencePolicy().evaluate(
        metadata, market="NSE", requested_use=api.DataUse.RESEARCH, programmatic_acquisition=True
    )

    assert decision.allowed is False
    assert api.DataLicenceReason.NSE_PROGRAMMATIC_ACQUISITION_PROHIBITED in decision.reasons


def test_decision_fingerprint_is_repeatable_and_binds_policy_inputs():
    api = _api()
    metadata = api.DataLicenceMetadata(
        source_id="vendor-a",
        licence_ref="lic-1",
        acquisition_permission=api.AcquisitionPermission.ALLOWED,
        permitted_uses=(api.DataUse.RESEARCH,),
        synthetic=False,
    )
    policy = api.DataLicencePolicy()
    first = policy.evaluate(metadata, market="BSE", requested_use=api.DataUse.RESEARCH, programmatic_acquisition=False)
    second = policy.evaluate(metadata, market="BSE", requested_use=api.DataUse.RESEARCH, programmatic_acquisition=False)
    changed = policy.evaluate(metadata, market="BSE", requested_use=api.DataUse.BACKTEST, programmatic_acquisition=False)

    assert first.allowed is True
    assert first.fingerprint == second.fingerprint
    assert first.fingerprint != changed.fingerprint
