from dashboard.backend.product_ops_v2.evidence import g9_markers

def test_g9_markers_preserve_authority_boundaries():
    markers=dict(g9_markers())
    assert markers['PRODUCT_OPS_AUTHORITY']=='PRIVACY_OPERATIONS_ONLY'
    assert markers['IDENTITY_AUTHORITY']=='S2_DEVICE_SESSION_GATE'
    assert markers['INCIDENT_AUTHORITY']=='FAILURE_INCIDENT_EXISTING_PATH'
    assert markers['APPROVED_ORDER_AUTHORITY']=='RISK_GATE_V2_ONLY'
    assert markers['LIVE_STATE']=='READ_ONLY/DISARMED'
    assert markers['G9_ENABLES_REAL_MONEY_TRADING']=='NO'
    assert markers['SOFTWARE_TESTS_PROVE_LEGAL_COMPLIANCE']=='NO'
