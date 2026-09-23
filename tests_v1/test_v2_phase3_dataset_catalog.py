from __future__ import annotations

from dataclasses import replace
from importlib import import_module

import pytest


def _api():
    try:
        return import_module("engine.data.catalog")
    except ModuleNotFoundError:
        pytest.fail("engine.data.catalog is missing", pytrace=False)


def _provenance(api, *, synthetic: bool = False):
    return api.DatasetProvenance(
        source_id="licensed-feed-a",
        source_type="licensed" if not synthetic else "synthetic",
        licence_id="lic-research-v1" if not synthetic else "synthetic-policy-v1",
        permitted_use="research",
        synthetic=synthetic,
        model_ref="" if not synthetic else "black76/v1",
    )


def _record(api, *, checksum: str = "a" * 64, synthetic: bool = False):
    return api.DatasetRecord.build(
        namespace="market",
        logical_name="nifty-1m-bars",
        data_kind="bars",
        schema_version="ohlcv/v1",
        content_sha256=checksum,
        provenance=_provenance(api, synthetic=synthetic),
        lineage=("raw:nifty-1m:2026-01",),
    )


def test_dataset_identity_and_version_are_deterministic_and_content_bound():
    api = _api()
    first = _record(api)
    same = _record(api)
    changed = _record(api, checksum="b" * 64)

    assert first.dataset_id == same.dataset_id
    assert first.version_id == same.version_id
    assert first.dataset_id.startswith("ds_")
    assert first.version_id.startswith("dsv_")
    assert changed.dataset_id == first.dataset_id
    assert changed.version_id != first.version_id


def test_record_carries_checksum_provenance_lineage_and_licence_evidence():
    api = _api()
    record = _record(api)

    assert record.content_sha256 == "a" * 64
    assert record.schema_version == "ohlcv/v1"
    assert record.lineage == ("raw:nifty-1m:2026-01",)
    assert record.provenance.source_id == "licensed-feed-a"
    assert record.provenance.licence_id == "lic-research-v1"
    assert record.provenance.permitted_use == "research"
    assert record.provenance.synthetic is False


def test_catalog_registration_is_idempotent_but_conflicting_evidence_fails_closed():
    api = _api()
    catalog = api.DatasetCatalog()
    record = _record(api)

    assert catalog.register(record) is record
    assert catalog.register(record) is record

    forged = replace(record, content_sha256="b" * 64)
    with pytest.raises(api.DatasetCatalogError, match="version identity"):
        catalog.register(forged)


def test_catalog_lookup_and_listing_are_deterministic():
    api = _api()
    catalog = api.DatasetCatalog()
    v2 = _record(api, checksum="b" * 64)
    v1 = _record(api, checksum="a" * 64)
    catalog.register(v2)
    catalog.register(v1)

    assert catalog.get(v1.dataset_id, v1.version_id) == v1
    assert catalog.versions(v1.dataset_id) == tuple(sorted((v1, v2), key=lambda item: item.version_id))
    assert catalog.list_records() == tuple(sorted((v1, v2), key=lambda item: (item.dataset_id, item.version_id)))


def test_invalid_checksum_and_duplicate_lineage_are_rejected():
    api = _api()
    with pytest.raises(api.DatasetCatalogError, match="sha256"):
        api.DatasetRecord.build(
            namespace="market",
            logical_name="nifty-1m-bars",
            data_kind="bars",
            schema_version="ohlcv/v1",
            content_sha256="not-a-sha",
            provenance=_provenance(api),
            lineage=(),
        )

    with pytest.raises(api.DatasetCatalogError, match="lineage"):
        api.DatasetRecord.build(
            namespace="market",
            logical_name="nifty-1m-bars",
            data_kind="bars",
            schema_version="ohlcv/v1",
            content_sha256="a" * 64,
            provenance=_provenance(api),
            lineage=("parent", "parent"),
        )


def test_synthetic_provenance_requires_model_reference():
    api = _api()
    with pytest.raises(api.DatasetCatalogError, match="model_ref"):
        api.DatasetProvenance(
            source_id="synthetic",
            source_type="synthetic",
            licence_id="synthetic-policy-v1",
            permitted_use="research",
            synthetic=True,
            model_ref="",
        )
