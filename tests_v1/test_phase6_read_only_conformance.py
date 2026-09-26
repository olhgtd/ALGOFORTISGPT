from __future__ import annotations

import importlib
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/'engine'/'broker_contract'/'read_only_conformance_v2.py'


def _load():
    assert MODULE.is_file(), 'Phase-6 read-only conformance kit is missing'
    return importlib.import_module('engine.broker_contract.read_only_conformance_v2')


class Profile:
    profile_id='ANGELONE/SMARTAPI/READ_ONLY'


class Good:
    adapter_id='angelone-v2-read-only'
    def capabilities(self): return frozenset({'profile','orders','trades','positions','funds','health'})
    def profile(self): return Profile()
    def orders(self): return ()
    def trades(self): return ()
    def positions(self): return ()
    def funds(self): return object()
    def health(self): return object()


def test_valid_read_only_shape_passes() -> None:
    m=_load()
    m.assert_read_only_broker_conformance(Good(), expected_broker='ANGELONE')


def test_missing_required_read_method_fails() -> None:
    m=_load()
    class Missing(Good):
        positions=None
    with pytest.raises(m.ReadOnlyBrokerConformanceError, match='positions'):
        m.assert_read_only_broker_conformance(Missing(), expected_broker='ANGELONE')


def test_any_callable_mutation_method_fails_conformance() -> None:
    m=_load()
    class Unsafe(Good):
        def cancel(self, order_id): return True
    with pytest.raises(m.ReadOnlyBrokerConformanceError, match='mutation'):
        m.assert_read_only_broker_conformance(Unsafe(), expected_broker='ANGELONE')


def test_broad_protocol_compatibility_is_not_a_reason_to_add_submit() -> None:
    m=_load()
    class Broad(Good):
        def submit(self, order): return order
    with pytest.raises(m.ReadOnlyBrokerConformanceError, match='submit'):
        m.assert_read_only_broker_conformance(Broad(), expected_broker='ANGELONE')


def test_wrong_broker_identity_fails() -> None:
    m=_load()
    with pytest.raises(m.ReadOnlyBrokerConformanceError, match='broker'):
        m.assert_read_only_broker_conformance(Good(), expected_broker='ZERODHA')
