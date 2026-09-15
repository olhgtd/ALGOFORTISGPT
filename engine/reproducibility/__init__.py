"""Versioned reproducibility identities and replay contracts (Slice 12).

Public exports are lazy so low-level domain code can use ``codec`` without
initializing market/portfolio-dependent reproducibility modules.
"""

from __future__ import annotations

from importlib import import_module


_EXPORTS = {
    "CanonicalCodec": ("engine.reproducibility.codec", "CanonicalCodec"),
    "CanonicalEncodingError": ("engine.reproducibility.codec", "CanonicalEncodingError"),
    "ApprovedRuntimeDependencyLock": ("engine.reproducibility.dependencies", "ApprovedRuntimeDependencyLock"),
    "DependencyDeclaration": ("engine.reproducibility.dependencies", "DependencyDeclaration"),
    "EnvironmentConformance": ("engine.reproducibility.dependencies", "EnvironmentConformance"),
    "RuntimeDependencyClosure": ("engine.reproducibility.dependencies", "RuntimeDependencyClosure"),
    "detect_parquet_backend_name": ("engine.reproducibility.dependencies", "detect_parquet_backend_name"),
    "detect_runtime_closure": ("engine.reproducibility.dependencies", "detect_runtime_closure"),
    "load_approved_runtime_lock": ("engine.reproducibility.dependencies", "load_approved_runtime_lock"),
    "runtime_conformance": ("engine.reproducibility.dependencies", "runtime_conformance"),
    "MarketDataPolicy": ("engine.reproducibility.market_data", "MarketDataPolicy"),
    "MarketDataSnapshot": ("engine.reproducibility.market_data", "MarketDataSnapshot"),
    "MarketDataStream": ("engine.reproducibility.market_data", "MarketDataStream"),
    "CategoryBManifestFailure": ("engine.reproducibility.model", "CategoryBManifestFailure"),
    "CategoryCOperationalFailure": ("engine.reproducibility.model", "CategoryCOperationalFailure"),
    "ReproducibilityManifest": ("engine.reproducibility.model", "ReproducibilityManifest"),
    "ResultEvidence": ("engine.reproducibility.model", "ResultEvidence"),
    "ResultEvidenceFamily": ("engine.reproducibility.model", "ResultEvidenceFamily"),
    "RandomizedAnalysisEntry": ("engine.reproducibility.model", "RandomizedAnalysisEntry"),
    "RandomizedAnalysisCollection": ("engine.reproducibility.model", "RandomizedAnalysisCollection"),
    "ValidationEvidenceEntry": ("engine.reproducibility.model", "ValidationEvidenceEntry"),
    "ValidationEvidenceCollection": ("engine.reproducibility.model", "ValidationEvidenceCollection"),
    "InvalidFinalizedResult": ("engine.reproducibility.model", "InvalidFinalizedResult"),
    "RuntimeConfigurationSnapshot": ("engine.reproducibility.model", "RuntimeConfigurationSnapshot"),
    "RuntimeIdentity": ("engine.reproducibility.model", "RuntimeIdentity"),
    "StructuredFailureResult": ("engine.reproducibility.model", "StructuredFailureResult"),
    "SuccessfulResult": ("engine.reproducibility.model", "SuccessfulResult"),
    "successful_result_v2": ("engine.reproducibility.model", "successful_result_v2"),
    "ReplayComparison": ("engine.reproducibility.replay", "ReplayComparison"),
    "ReplayStatus": ("engine.reproducibility.replay", "ReplayStatus"),
    "verify_replay": ("engine.reproducibility.replay", "verify_replay"),
    "SourceIdentityPolicy": ("engine.reproducibility.source", "SourceIdentityPolicy"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    """Resolve the established public surface without eager package coupling."""
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as error:
        raise AttributeError(name) from error
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))
