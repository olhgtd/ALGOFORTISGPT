"""Phase 8.5-B — historical-data acquisition boundary (ADR §129).

This module is an ACQUISITION/PROVENANCE layer over the EXISTING canonical
importer authorities (§129.1).  It never duplicates discovery, detection,
cleaning, storage, or reporting: it feeds them.

Frozen contracts implemented here:
- §129.9/§129.11 raw source evidence is immutable and preserved.
- §129.13 deterministic acquisition manifests with checksum/provenance.
- §129.15 structured dataset identity (no ambiguous string concatenation).
- §129.16 same source checksum + same canonical targets ⇒ ALREADY_IMPORTED
  no-op; changed content ⇒ new fingerprint + supersession evidence recorded,
  canonical history never silently overwritten.

Out of scope here: Gap/calendar semantics.  Per the Phase 8.5 Slice-5 owner
decision, session-gap classification is owned exclusively by the
authoritative ``engine.market.calendar`` abstraction (consumed via
``engine.data.feeds.gap_analysis``); no calendar logic may live in
acquisition/importer modules.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from engine.data.feeds.importer_reporting import IMPORT_REPORT_ROOT, ImportManifest
from engine.reproducibility.codec import CanonicalCodec

ACQUISITION_CONTRACT_VERSION = "sentinelx-acquisition/v1"
PARSER_IDENTITY = "sentinelx.importer_orchestrator/v1"


# ------------------------------------------------------------------
# §129.9 — raw source evidence (immutable, never mutated)
# ------------------------------------------------------------------

def sha256_source_file(path: Path) -> tuple[str, int]:
    """Return ``(sha256_hexdigest, byte_size)`` for one source file.

    The file is streamed; source evidence is never mutated.
    """
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


# ------------------------------------------------------------------
# §129.13 / §129.16 — import fingerprint (reuses CanonicalCodec)
# ------------------------------------------------------------------

def compute_import_fingerprint(
    *,
    source_checksum_sha256: str,
    parser_identity: str,
    canonical_target_semantics: tuple[tuple[str, str], ...],
    mapping_config_fingerprint: str | None = None,
) -> str:
    """Deterministic import fingerprint via CanonicalCodec.

    This is the canonical identity for idempotency and supersession.
    All approved identity components participate; changing any one
    produces a distinct fingerprint.

    Fingerprint fields (real authorities only, no synthetic aliases):
    - acquisition_contract_version: frozen contract version string
    - parser_identity: parser/adapter identity (includes version suffix)
    - source_checksum_sha256: SHA-256 of source file bytes
    - canonical_target_semantics: deterministic ordered tuple of
      (canonical_output_path, resolved_source_timezone) for every
      resolved CanonicalIdentity.  Binds timezone semantics that
      affect stored data but are absent from the target path.
    - mapping_config_fingerprint: optional, for future mapping/config identity

    Uses the established ``CanonicalCodec.fingerprint`` — no second
    fingerprint authority is introduced.
    """
    fields: list[tuple[str, object]] = [
        ("acquisition_contract_version", ACQUISITION_CONTRACT_VERSION),
        ("parser_identity", parser_identity),
        ("source_checksum_sha256", source_checksum_sha256),
        ("canonical_target_semantics", tuple(sorted(canonical_target_semantics))),
    ]
    if mapping_config_fingerprint is not None:
        fields.append(("mapping_config_fingerprint", mapping_config_fingerprint))
    return CanonicalCodec.fingerprint(
        "sentinelx-import-fingerprint/v1",
        tuple(fields),
    )


# ------------------------------------------------------------------
# §129.13 — import identity key (for idempotency lookup)
# ------------------------------------------------------------------

def compute_import_identity_key(
    *,
    source_checksum_sha256: str,
    parser_identity: str,
    canonical_target_semantics: tuple[tuple[str, str], ...],
    mapping_config_fingerprint: str | None = None,
) -> str:
    """Canonical import identity key for exact idempotency lookup.

    The key is the import fingerprint itself — same identity components
    ⇒ same key ⇒ ALREADY_IMPORTED deterministic no-op.
    """
    return compute_import_fingerprint(
        source_checksum_sha256=source_checksum_sha256,
        parser_identity=parser_identity,
        canonical_target_semantics=canonical_target_semantics,
        mapping_config_fingerprint=mapping_config_fingerprint,
    )


# ------------------------------------------------------------------
# §129.16 — idempotency lookup over prior accepted manifests
# ------------------------------------------------------------------

def check_already_imported(
    import_fingerprint: str,
    prior_manifests: list[ImportManifest],
) -> ImportManifest | None:
    """Deterministic lookup over prior accepted manifests.

    Returns the matching accepted manifest if ALL identity components
    match an already-imported record with status ``"imported"``.
    Returns ``None`` if no match or if the prior record was
    quarantined/failed (a prior failure never satisfies idempotency).

    Caller must still verify that the source can be parsed enough to
    resolve its canonical identity before treating the result as valid.
    """
    for manifest in prior_manifests:
        if (
            manifest.import_fingerprint == import_fingerprint
            and manifest.status == "imported"
            and manifest.source_checksum_sha256 is not None
        ):
            return manifest
    return None


# ------------------------------------------------------------------
# §129.11 / §129.16 — supersession evidence
# ------------------------------------------------------------------

def record_supersession(
    *,
    prior_manifests: list[ImportManifest],
    current_source_checksum_sha256: str,
    canonical_targets: tuple[str, ...],
) -> str | None:
    """Find the prior accepted checksum for the same canonical targets.

    When the same source filename has changed bytes, the caller needs
    the prior accepted checksum for supersession evidence.  This
    function scans prior manifests for the most recent accepted import
    targeting the same canonical output paths.

    Returns the prior accepted ``source_checksum_sha256`` if found,
    or ``None`` if no prior accepted import exists for these targets.
    """
    prior: str | None = None
    current_targets = set(canonical_targets)
    for manifest in prior_manifests:
        if manifest.status != "imported":
            continue
        if manifest.source_checksum_sha256 is None:
            continue
        manifest_targets = set(manifest.output_paths)
        if manifest_targets == current_targets:
            prior = manifest.source_checksum_sha256
    return prior


# ------------------------------------------------------------------
# §129.16 — duplicate conflict evidence (keep-first preserved)
# ------------------------------------------------------------------

def detect_duplicate_conflicts(
    accepted_dataframe: object,
    duplicate_mask: object,
) -> int:
    """Count disagreeing OHLCV values within duplicate timestamp groups.

    This records deterministic conflict evidence ONLY.  It does NOT
    change the existing frozen keep-first resolution semantics
    (OD-8.5-04).  The canonical stored winner is never altered.

    Args:
        accepted_dataframe: The DataFrame after keep-first deduplication.
        duplicate_mask: Boolean mask identifying rows that were part of
            a duplicate group (removed during keep-first).

    Returns:
        Count of duplicate rows whose OHLCV values differ from the
        kept (winner) row in the same timestamp group.  This is the
        ``duplicate_conflicts_removed`` manifest field.
    """
    import pandas as pd

    if not isinstance(accepted_dataframe, pd.DataFrame):
        return 0
    if not isinstance(duplicate_mask, pd.Series):
        return 0

    if duplicate_mask.sum() == 0:
        return 0

    df = accepted_dataframe
    conflicts = 0
    ohlcv_cols = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]

    if not ohlcv_cols or "timestamp" not in df.columns:
        return 0

    try:
        removed_rows = df[duplicate_mask]
        for _, removed_row in removed_rows.iterrows():
            ts = removed_row.get("timestamp")
            if ts is None:
                continue
            matching_kept = df[(~duplicate_mask) & (df["timestamp"] == ts)]
            if matching_kept.empty:
                continue
            kept_row = matching_kept.iloc[0]
            if not all(kept_row[col] == removed_row[col] for col in ohlcv_cols):
                conflicts += 1
    except Exception:
        return 0

    return conflicts
