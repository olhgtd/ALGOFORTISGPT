from pathlib import Path
from importlib import import_module
import pytest

def _guard():
    try: return import_module('build.tools.check_phase8_ai_intelligence')
    except ModuleNotFoundError: pytest.fail('check_phase8_ai_shadow is missing',pytrace=False)

def test_qualification_requirements_fail_when_artifact_missing(tmp_path):
    guard=_guard(); root=tmp_path
    (root/'engine/ai/v2').mkdir(parents=True)
    missing=guard.check_qualification_artifacts(root)
    assert 'engine/ai/v2/evidence.py' in missing
    assert '.github/workflows/v2-phase8-ai-intelligence.yml' in missing

def test_workflow_requires_dual_windows_probe_and_compare(tmp_path):
    guard=_guard(); wf=tmp_path/'.github/workflows'; wf.mkdir(parents=True)
    p=wf/'v2-phase8-ai-intelligence.yml'; p.write_text('runs-on: windows-latest\n',encoding='utf-8')
    findings=guard.check_g8_workflow(p)
    assert any('windows-2022' in x for x in findings)
    assert any('compare' in x.lower() for x in findings)
