from pathlib import Path
import textwrap


def test_guard_rejects_forbidden_authority_and_direct_network(tmp_path):
    from build.tools.check_phase8_ai_intelligence import scan_phase8_tree
    root = tmp_path / 'engine' / 'ai' / 'v2'; root.mkdir(parents=True)
    (root/'bad.py').write_text(textwrap.dedent('''
        from engine.broker_adapters import x
        from engine.orders.contracts_v2 import ApprovedOrder
        ApprovedOrder(None)
        import requests
    '''), encoding='utf-8')
    findings = scan_phase8_tree(tmp_path)
    joined='\n'.join(findings)
    assert 'broker' in joined.lower()
    assert 'ApprovedOrder' in joined
    assert 'network' in joined.lower() or 'requests' in joined.lower()


def test_guard_allows_contract_only_module(tmp_path):
    from build.tools.check_phase8_ai_intelligence import scan_phase8_tree
    root=tmp_path/'engine'/'ai'/'v2'; root.mkdir(parents=True)
    (root/'contracts.py').write_text('from dataclasses import dataclass\n', encoding='utf-8')
    assert scan_phase8_tree(tmp_path) == ()


def test_guard_allows_forbidden_data_class_labels_without_secret_store_access(tmp_path):
    from build.tools.check_phase8_ai_intelligence import scan_phase8_tree
    root=tmp_path/'engine'/'ai'/'v2'; root.mkdir(parents=True)
    (root/'contracts.py').write_text('PRIVATE_KEY = "PRIVATE_KEY"\nBROKER_CREDENTIAL = "BROKER_CREDENTIAL"\n', encoding='utf-8')
    assert scan_phase8_tree(tmp_path) == ()


def test_guard_allows_pure_url_parsing_but_rejects_url_network_access(tmp_path):
    from build.tools.check_phase8_ai_intelligence import scan_phase8_tree
    root=tmp_path/'engine'/'ai'/'v2'; root.mkdir(parents=True)
    (root/'safe.py').write_text('from urllib.parse import urlsplit, urlunsplit\n', encoding='utf-8')
    assert scan_phase8_tree(tmp_path) == ()
    (root/'bad.py').write_text('from urllib.request import urlopen\n', encoding='utf-8')
    findings = scan_phase8_tree(tmp_path)
    assert any('network' in item.lower() and 'urllib' in item.lower() for item in findings)
