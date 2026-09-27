from engine.data import licensing as l


def meta(permission=None, uses=None):
    kwargs = dict(source_id='licensed-feed', licence_ref='terms-v4', acquisition_permission=l.AcquisitionPermission.ALLOWED,
                  permitted_uses=uses or (l.DataUse.RESEARCH,), synthetic=False)
    if permission is not None:
        kwargs['external_processing_permission'] = permission
    return l.DataLicenceMetadata(**kwargs)


def test_external_processing_missing_unknown_and_prohibited_fail_closed():
    p=l.DataLicencePolicy()
    missing=l.DataLicenceMetadata('s','lic',l.AcquisitionPermission.ALLOWED,(l.DataUse.RESEARCH,),False,None)
    assert not p.evaluate_external_processing(missing, requested_use=l.DataUse.RESEARCH).allowed
    assert not p.evaluate_external_processing(meta(l.ExternalProcessingPermission.UNKNOWN), requested_use=l.DataUse.RESEARCH).allowed
    assert not p.evaluate_external_processing(meta(l.ExternalProcessingPermission.PROHIBITED), requested_use=l.DataUse.RESEARCH).allowed


def test_external_processing_allowed_requires_requested_use_and_is_deterministic():
    p=l.DataLicencePolicy(); m=meta(l.ExternalProcessingPermission.ALLOWED)
    a=p.evaluate_external_processing(m, requested_use=l.DataUse.RESEARCH)
    b=p.evaluate_external_processing(m, requested_use=l.DataUse.RESEARCH)
    denied=p.evaluate_external_processing(m, requested_use=l.DataUse.BACKTEST)
    assert a.allowed and a.fingerprint == b.fingerprint
    assert not denied.allowed and a.fingerprint != denied.fingerprint
