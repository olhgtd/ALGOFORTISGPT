"""Immutable, deterministic dataset catalog contracts for AlgoFortis V2."""

from __future__ import annotations

from dataclasses import dataclass
import re

from engine.reproducibility.codec import CanonicalCodec


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DatasetCatalogError(ValueError):
    """Raised when dataset evidence is invalid, ambiguous, or mutable."""


def _required_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DatasetCatalogError(f"{name} must be non-empty")
    return value.strip()


def _dataset_id(namespace: str, logical_name: str, data_kind: str) -> str:
    digest = CanonicalCodec.fingerprint(
        "algofortis-dataset-id/v1",
        (
            ("namespace", namespace),
            ("logical_name", logical_name),
            ("data_kind", data_kind),
        ),
    )
    return f"ds_{digest}"


@dataclass(frozen=True, slots=True)
class DatasetProvenance:
    source_id: str
    source_type: str
    licence_id: str
    permitted_use: str
    synthetic: bool = False
    model_ref: str = ""

    def __post_init__(self) -> None:
        for field_name in ("source_id", "source_type", "licence_id", "permitted_use"):
            object.__setattr__(self, field_name, _required_text(field_name, getattr(self, field_name)))
        if not isinstance(self.synthetic, bool):
            raise DatasetCatalogError("synthetic must be bool")
        if not isinstance(self.model_ref, str):
            raise DatasetCatalogError("model_ref must be a string")
        normalized_model_ref = self.model_ref.strip()
        if self.synthetic and not normalized_model_ref:
            raise DatasetCatalogError("synthetic provenance requires model_ref")
        object.__setattr__(self, "model_ref", normalized_model_ref)

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-dataset-provenance/v1",
            (
                ("source_id", self.source_id),
                ("source_type", self.source_type),
                ("licence_id", self.licence_id),
                ("permitted_use", self.permitted_use),
                ("synthetic", self.synthetic),
                ("model_ref", self.model_ref),
            ),
        )


@dataclass(frozen=True, slots=True)
class DatasetRecord:
    dataset_id: str
    version_id: str
    namespace: str
    logical_name: str
    data_kind: str
    schema_version: str
    content_sha256: str
    provenance: DatasetProvenance
    lineage: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "dataset_id",
            "version_id",
            "namespace",
            "logical_name",
            "data_kind",
            "schema_version",
        ):
            object.__setattr__(self, field_name, _required_text(field_name, getattr(self, field_name)))
        if not isinstance(self.content_sha256, str) or not _SHA256_RE.fullmatch(self.content_sha256):
            raise DatasetCatalogError("content_sha256 must be lowercase sha256")
        if not isinstance(self.provenance, DatasetProvenance):
            raise DatasetCatalogError("provenance must be DatasetProvenance")
        lineage = tuple(self.lineage)
        if any(not isinstance(item, str) or not item.strip() for item in lineage):
            raise DatasetCatalogError("lineage entries must be non-empty strings")
        lineage = tuple(item.strip() for item in lineage)
        if len(lineage) != len(set(lineage)):
            raise DatasetCatalogError("lineage entries must be unique")
        object.__setattr__(self, "lineage", lineage)

    @classmethod
    def build(
        cls,
        *,
        namespace: str,
        logical_name: str,
        data_kind: str,
        schema_version: str,
        content_sha256: str,
        provenance: DatasetProvenance,
        lineage: tuple[str, ...] = (),
    ) -> "DatasetRecord":
        namespace = _required_text("namespace", namespace)
        logical_name = _required_text("logical_name", logical_name)
        data_kind = _required_text("data_kind", data_kind)
        schema_version = _required_text("schema_version", schema_version)
        if not isinstance(content_sha256, str) or not _SHA256_RE.fullmatch(content_sha256):
            raise DatasetCatalogError("content_sha256 must be lowercase sha256")
        if not isinstance(provenance, DatasetProvenance):
            raise DatasetCatalogError("provenance must be DatasetProvenance")
        lineage = tuple(lineage)
        if any(not isinstance(item, str) or not item.strip() for item in lineage):
            raise DatasetCatalogError("lineage entries must be non-empty strings")
        lineage = tuple(item.strip() for item in lineage)
        if len(lineage) != len(set(lineage)):
            raise DatasetCatalogError("lineage entries must be unique")

        dataset_id = _dataset_id(namespace, logical_name, data_kind)
        version_id = cls._version_id_for(
            dataset_id=dataset_id,
            schema_version=schema_version,
            content_sha256=content_sha256,
            provenance=provenance,
            lineage=lineage,
        )
        return cls(
            dataset_id=dataset_id,
            version_id=version_id,
            namespace=namespace,
            logical_name=logical_name,
            data_kind=data_kind,
            schema_version=schema_version,
            content_sha256=content_sha256,
            provenance=provenance,
            lineage=lineage,
        )

    @staticmethod
    def _version_id_for(
        *,
        dataset_id: str,
        schema_version: str,
        content_sha256: str,
        provenance: DatasetProvenance,
        lineage: tuple[str, ...],
    ) -> str:
        digest = CanonicalCodec.fingerprint(
            "algofortis-dataset-version/v1",
            (
                ("dataset_id", dataset_id),
                ("schema_version", schema_version),
                ("content_sha256", content_sha256),
                ("provenance", provenance.fingerprint),
                ("lineage", lineage),
            ),
        )
        return f"dsv_{digest}"

    @property
    def expected_dataset_id(self) -> str:
        return _dataset_id(self.namespace, self.logical_name, self.data_kind)

    @property
    def expected_version_id(self) -> str:
        return self._version_id_for(
            dataset_id=self.dataset_id,
            schema_version=self.schema_version,
            content_sha256=self.content_sha256,
            provenance=self.provenance,
            lineage=self.lineage,
        )


class DatasetCatalog:
    """In-memory immutable registration authority for dataset-version evidence."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], DatasetRecord] = {}

    def register(self, record: DatasetRecord) -> DatasetRecord:
        if not isinstance(record, DatasetRecord):
            raise DatasetCatalogError("record must be DatasetRecord")
        if record.dataset_id != record.expected_dataset_id:
            raise DatasetCatalogError("dataset identity does not match record evidence")
        if record.version_id != record.expected_version_id:
            raise DatasetCatalogError("version identity does not match record evidence")

        key = (record.dataset_id, record.version_id)
        existing = self._records.get(key)
        if existing is not None:
            if existing != record:
                raise DatasetCatalogError("dataset version is immutable and conflicts with existing evidence")
            return existing
        self._records[key] = record
        return record

    def get(self, dataset_id: str, version_id: str) -> DatasetRecord:
        try:
            return self._records[(dataset_id, version_id)]
        except KeyError as exc:
            raise DatasetCatalogError("dataset version is not registered") from exc

    def versions(self, dataset_id: str) -> tuple[DatasetRecord, ...]:
        return tuple(
            sorted(
                (record for record in self._records.values() if record.dataset_id == dataset_id),
                key=lambda record: record.version_id,
            )
        )

    def list_records(self) -> tuple[DatasetRecord, ...]:
        return tuple(sorted(self._records.values(), key=lambda record: (record.dataset_id, record.version_id)))
