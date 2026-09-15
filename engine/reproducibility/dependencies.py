"""DependencyIdentity/v1 declarations, detection, and conformance boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from importlib import metadata
import json
from pathlib import Path
from typing import Callable, Iterable

from engine.reproducibility.codec import CanonicalCodec


def _name(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip().lower().replace("_", "-")


@dataclass(frozen=True, order=True)
class RuntimeDependency:
    name: str
    version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _name(self.name, "dependency name"))
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("dependency version must be non-empty")
        object.__setattr__(self, "version", self.version.strip())


@dataclass(frozen=True)
class DependencyDeclaration:
    """Declared economic runtime dependencies; excludes unrelated installed packages."""

    version: str
    dependencies: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("dependency declaration version must be non-empty")
        values = tuple(sorted(_name(item, "declared dependency") for item in self.dependencies))
        if not values or len(values) != len(set(values)):
            raise ValueError("declared dependencies must be non-empty and unique")
        object.__setattr__(self, "dependencies", values)

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "sentinelx-dependency-declaration/v1",
            (("version", self.version), ("dependencies", self.dependencies)),
        )


@dataclass(frozen=True)
class RuntimeDependencyClosure:
    """The actually detected dependency closure used by an execution."""

    policy_version: str
    dependencies: tuple[RuntimeDependency, ...]
    parquet_backend: RuntimeDependency | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("dependency policy version must be non-empty")
        values = tuple(sorted(self.dependencies))
        if not values or not all(isinstance(value, RuntimeDependency) for value in values):
            raise ValueError("runtime dependency closure must contain RuntimeDependency values")
        if len({value.name for value in values}) != len(values):
            raise ValueError("runtime dependency closure names must be unique")
        if self.parquet_backend is not None and not isinstance(self.parquet_backend, RuntimeDependency):
            raise TypeError("parquet_backend must be RuntimeDependency or None")
        object.__setattr__(self, "dependencies", values)

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "sentinelx-runtime-dependency-closure/v1",
            (
                ("policy_version", self.policy_version),
                ("dependencies", tuple((item.name, item.version) for item in self.dependencies)),
                ("parquet_backend", None if self.parquet_backend is None else (self.parquet_backend.name, self.parquet_backend.version)),
            ),
        )


class EnvironmentConformance(str, Enum):
    CONFORMANT = "CONFORMANT"
    NONCONFORMANT = "NONCONFORMANT"


@dataclass(frozen=True)
class ApprovedRuntimeDependencyLock:
    """Approved baseline, distinct from both declaration and detected closure."""

    schema_version: str
    python_implementation: str
    python_version: str
    closure: RuntimeDependencyClosure

    def __post_init__(self) -> None:
        for field_name in ("schema_version", "python_implementation", "python_version"):
            if not isinstance(getattr(self, field_name), str) or not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if not isinstance(self.closure, RuntimeDependencyClosure):
            raise TypeError("closure must be RuntimeDependencyClosure")

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "sentinelx-approved-runtime-lock/v1",
            (("schema_version", self.schema_version),
             ("python_implementation", self.python_implementation),
             ("python_version", self.python_version),
             ("closure", self.closure.fingerprint)),
        )


def load_approved_runtime_lock(path: Path) -> ApprovedRuntimeDependencyLock:
    """Load the closed, versioned approved baseline; reject extra/partial fields."""
    try:
        body = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("approved runtime lock cannot be read") from error
    if not isinstance(body, dict) or set(body) != {"schema_version", "python_runtime", "dependency_policy_version", "dependencies", "parquet_backend"}:
        raise ValueError("approved runtime lock has an invalid schema")
    runtime = body["python_runtime"]
    backend = body["parquet_backend"]
    dependencies = body["dependencies"]
    if not isinstance(runtime, dict) or set(runtime) != {"implementation", "version"}:
        raise ValueError("approved runtime lock has invalid Python identity")
    if not isinstance(backend, dict) or set(backend) != {"name", "version"}:
        raise ValueError("approved runtime lock has invalid Parquet backend")
    if not isinstance(dependencies, list) or not all(isinstance(item, dict) and set(item) == {"name", "version"} for item in dependencies):
        raise ValueError("approved runtime lock has invalid dependency list")
    closure = RuntimeDependencyClosure(
        body["dependency_policy_version"],
        tuple(RuntimeDependency(item["name"], item["version"]) for item in dependencies),
        RuntimeDependency(backend["name"], backend["version"]),
    )
    if closure.parquet_backend.name not in {item.name for item in closure.dependencies}:
        raise ValueError("approved Parquet backend must be in the approved dependency closure")
    return ApprovedRuntimeDependencyLock(body["schema_version"], runtime["implementation"], runtime["version"], closure)


def conformance(actual: RuntimeDependencyClosure, approved_lock_fingerprint: str) -> EnvironmentConformance:
    if not isinstance(actual, RuntimeDependencyClosure):
        raise TypeError("actual must be RuntimeDependencyClosure")
    if not isinstance(approved_lock_fingerprint, str) or not approved_lock_fingerprint:
        raise ValueError("approved lock fingerprint must be non-empty")
    return EnvironmentConformance.CONFORMANT if actual.fingerprint == approved_lock_fingerprint else EnvironmentConformance.NONCONFORMANT


def runtime_conformance(
    actual: RuntimeDependencyClosure,
    *,
    python_implementation: str,
    python_version: str,
    approved_lock: ApprovedRuntimeDependencyLock,
) -> EnvironmentConformance:
    """Compare the actual detected closure and runtime with an approved baseline."""
    if not isinstance(actual, RuntimeDependencyClosure) or not isinstance(approved_lock, ApprovedRuntimeDependencyLock):
        raise TypeError("actual and approved_lock must be dependency contracts")
    if not isinstance(python_implementation, str) or not python_implementation.strip():
        raise ValueError("python_implementation must be non-empty")
    if not isinstance(python_version, str) or not python_version.strip():
        raise ValueError("python_version must be non-empty")
    if (
        actual.fingerprint == approved_lock.closure.fingerprint
        and python_implementation == approved_lock.python_implementation
        and python_version == approved_lock.python_version
    ):
        return EnvironmentConformance.CONFORMANT
    return EnvironmentConformance.NONCONFORMANT


def detect_runtime_closure(
    declaration: DependencyDeclaration,
    *,
    policy_version: str,
    distribution_version: Callable[[str], str] = metadata.version,
    parquet_backend_name: str | None = None,
) -> RuntimeDependencyClosure:
    """Detect only declared dependencies; never fingerprint whole-machine packages."""
    if not isinstance(declaration, DependencyDeclaration):
        raise TypeError("declaration must be DependencyDeclaration")
    discovered: list[RuntimeDependency] = []
    for name in declaration.dependencies:
        try:
            discovered.append(RuntimeDependency(name, distribution_version(name)))
        except metadata.PackageNotFoundError as error:
            raise ValueError(f"required runtime dependency cannot be identified: {name}") from error
    backend_name = parquet_backend_name or detect_parquet_backend_name()
    try:
        backend = RuntimeDependency(_name(backend_name, "parquet backend"), distribution_version(_name(backend_name, "parquet backend")))
    except metadata.PackageNotFoundError as error:
        raise ValueError(f"required parquet backend cannot be identified: {backend_name}") from error
    return RuntimeDependencyClosure(policy_version, tuple(discovered), backend)


def detect_parquet_backend_name() -> str:
    """Identify pandas' selected Parquet engine without guessing from packages."""
    try:
        import pandas as pd
        engine = pd.io.parquet.get_engine("auto")
    except Exception as error:
        raise ValueError("required pandas Parquet backend cannot be identified") from error
    class_name = type(engine).__name__.casefold()
    if "pyarrow" in class_name:
        return "pyarrow"
    if "fastparquet" in class_name:
        return "fastparquet"
    raise ValueError("pandas selected an unsupported/unidentified Parquet backend")
