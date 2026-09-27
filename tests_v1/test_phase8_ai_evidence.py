from importlib import import_module
import pytest

def _api():
    try: return import_module('engine.ai.v2.evidence')
    except ModuleNotFoundError: pytest.fail('engine.ai.v2.evidence is missing', pytrace=False)

def test_all_required_g8_markers_present_and_validated():
    api=_api(); ev=api.build_g8_evidence(); text=ev.text()
    for marker in api.REQUIRED_G8_MARKERS: assert marker in text
    api.validate_g8_markers(tuple(api.REQUIRED_G8_MARKERS))

def test_missing_or_changed_marker_fails_closed():
    api=_api(); markers=list(api.REQUIRED_G8_MARKERS); markers.pop()
    with pytest.raises(api.G8EvidenceError): api.validate_g8_markers(tuple(markers))
    markers=list(api.REQUIRED_G8_MARKERS); markers[0]='AI_AUTHORITY=AUTONOMOUS'
    with pytest.raises(api.G8EvidenceError): api.validate_g8_markers(tuple(markers))

def test_g8_evidence_fingerprint_is_deterministic():
    api=_api(); assert api.build_g8_evidence().fingerprint == api.build_g8_evidence().fingerprint
