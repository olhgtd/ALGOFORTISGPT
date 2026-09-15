"""Source-file orchestration for the historical-data importer."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

import pandas as pd

from engine.data.feeds.importer_detection import (
    detect_contract_identities,
    detect_source_format,
    normalize_column_aliases,
    parse_filename_metadata,
    resolve_timeframe,
)
from engine.data.feeds.importer_discovery import discover_incoming_files
from engine.data.feeds.importer_reporting import (
    IMPORT_REPORT_ROOT,
    ImportManifest,
    build_import_manifest,
    build_quarantine_manifest,
    claim_import_run,
    write_import_manifest,
)
from engine.data.feeds.canonical_lock import canonical_target_claim
from engine.data.feeds.importer_storage import CANONICAL_STORAGE_ROOT, resolve_storage_path
from engine.data.feeds.ingestion import clean_ohlcv, write_ohlcv_parquet
from engine.market.calendar import ContractLifecycleEvidence, MarketCalendarAuthority


def read_source_file(source_file: Path) -> pd.DataFrame:
    """Read one approved incoming-file format into a DataFrame.

    Spreadsheet files (.xlsx and .xls) explicitly parse the first worksheet
    (sheet_name=0) as the authoritative tabular dataset. Contract-level
    partitioning for options/futures remains row-based downstream.
    """
    readers = {
        ".csv": pd.read_csv,
        ".xlsx": lambda path: pd.read_excel(path, engine="openpyxl", sheet_name=0),
        ".xls": lambda path: pd.read_excel(path, engine="xlrd", sheet_name=0),
        ".parquet": pd.read_parquet,
    }
    try:
        return readers[source_file.suffix.casefold()](source_file)
    except KeyError as error:
        raise ValueError(f"Unsupported importer file type: {source_file.suffix}") from error


def _merge_with_existing_canonical_data(
    incoming_data: pd.DataFrame,
    output_path: Path,
    *,
    timezone: str,
    instrument: str,
    timeframe: str,
    on_existing_read: Callable[[Path, int], None] | None = None,
) -> tuple[pd.DataFrame, int, int]:
    """Preserve existing canonical history, keeping the established first duplicate."""
    if not output_path.exists():
        return incoming_data, 0, 0

    existing_data = pd.read_parquet(output_path)
    if on_existing_read is not None:
        on_existing_read(output_path, len(existing_data))
    merged_data, duplicates_removed, invalid_rows = clean_ohlcv(
        pd.concat([existing_data, incoming_data], ignore_index=True),
        duplicate_columns=["timestamp"],
        timezone=timezone,
        instrument=instrument,
        timeframe=timeframe,
    )
    return (
        merged_data.sort_values("timestamp", kind="stable").reset_index(drop=True),
        duplicates_removed,
        invalid_rows,
    )


# ---------------------------------------------------------------------------
# §129.16 — prior manifest loading for idempotency lookup
# ---------------------------------------------------------------------------

def _load_prior_import_manifests() -> list[ImportManifest]:
    """Load all prior import manifests from the canonical report directory.

    Used by the idempotency lookup to find an exact import fingerprint match.
    Returns an empty list when no reports exist (first run, or clean state).
    """
    if not IMPORT_REPORT_ROOT.is_dir():
        return []
    manifests: list[ImportManifest] = []
    for path in sorted(IMPORT_REPORT_ROOT.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Only consider sub-run manifests (run_id-N format), skip parent run markers
            if "." not in path.stem or path.stem.rsplit(".", 1)[-1] == "json":
                manifests.append(ImportManifest(**data))
        except (json.JSONDecodeError, TypeError, KeyError):
            continue
    return manifests


def _compute_source_evidence(source_file: Path) -> tuple[str, int]:
    """§129.9 — compute immutable source checksum and byte size."""
    from engine.data.feeds.acquisition import sha256_source_file
    return sha256_source_file(source_file)


def _compute_fingerprint(
    *,
    source_checksum_sha256: str,
    canonical_target_semantics: tuple[tuple[str, str], ...],
) -> str:
    """§129.13 — compute import fingerprint via CanonicalCodec."""
    from engine.data.feeds.acquisition import (
        PARSER_IDENTITY,
        compute_import_fingerprint,
    )
    return compute_import_fingerprint(
        source_checksum_sha256=source_checksum_sha256,
        parser_identity=PARSER_IDENTITY,
        canonical_target_semantics=canonical_target_semantics,
    )


def _find_prior_accepted_manifest(
    import_fingerprint: str,
    prior_manifests: list[ImportManifest],
) -> ImportManifest | None:
    """§129.16 — find prior accepted manifest with matching fingerprint."""
    for manifest in prior_manifests:
        if (
            manifest.import_fingerprint == import_fingerprint
            and manifest.status == "imported"
            and manifest.source_checksum_sha256 is not None
        ):
            return manifest
    return None


def _find_supersession_prior(
    prior_manifests: list[ImportManifest],
    current_source_checksum: str,
    canonical_targets: tuple[str, ...],
) -> str | None:
    """§129.16 — find prior accepted checksum for supersession evidence."""
    from engine.data.feeds.acquisition import record_supersession
    return record_supersession(
        prior_manifests=prior_manifests,
        current_source_checksum_sha256=current_source_checksum,
        canonical_targets=canonical_targets,
    )


def _compute_duplicate_conflicts(
    raw_data: pd.DataFrame,
    cleaned_data: pd.DataFrame,
    output_path: Path,
    *,
    timezone: str,
    instrument: str,
    timeframe: str,
) -> int:
    """§129.16 — count duplicate conflicts for one identity's output."""
    from engine.data.feeds.acquisition import detect_duplicate_conflicts

    if "timestamp" not in raw_data.columns:
        return 0
    try:
        # Build a mask of rows removed during keep-first deduplication
        df = raw_data.copy()
        from engine.data.feeds.data_cleaning import normalize_timestamps
        normalize_timestamps(df, timezone)
        ts_before = df["timestamp"].tolist()
        ts_after = cleaned_data["timestamp"].tolist() if "timestamp" in cleaned_data.columns else []
        if len(ts_before) == len(ts_after):
            return 0  # no rows removed → no duplicates
        # Build mask: True for rows that were removed (not in cleaned output)
        # Simple approach: mark rows whose timestamp doesn't appear in cleaned output
        cleaned_ts_set = set(ts_after)
        mask = pd.Series([ts not in cleaned_ts_set for ts in ts_before])
        return detect_duplicate_conflicts(df, mask)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# §129.17 — authoritative session-gap evidence (Phase 8.5 Slice 5)
#
# All calendar/session semantics live in the single authoritative
# engine.market.calendar authority.  This orchestration layer only resolves
# WHICH offline dataset applies, injects explicitly supplied lifecycle
# evidence, and records deterministic evidence fields on the manifest.
# It never guesses holidays/sessions and never mutates canonical data.
# ---------------------------------------------------------------------------

_GAP_EVIDENCE_MAX_SAMPLES = 20


def _resolve_gap_authority(
    markets: Iterable[str],
    calendar_authority: MarketCalendarAuthority | None,
    *,
    data_root: Path | None = None,
) -> tuple[dict[str, MarketCalendarAuthority | None], bool]:
    """Resolve one offline calendar authority per market tag (fail closed).

    Only owner-approved mappings auto-resolve; any other market yields NO
    authority so every analyzed date fails closed to CALENDAR_UNAVAILABLE.
    Returns ``(authority_by_market, attempted_offline_load)`` where the flag
    records whether any offline lookup was attempted at all.
    """
    from engine.data.feeds.gap_analysis import DEFAULT_OFFLINE_CALENDAR_BY_MARKET

    resolved: dict[str, MarketCalendarAuthority | None] = {}
    attempted = False
    for market in sorted(set(markets)):
        if calendar_authority is not None:
            resolved[market] = calendar_authority
            continue
        calendar_id = DEFAULT_OFFLINE_CALENDAR_BY_MARKET.get(market)
        if calendar_id is None:
            resolved[market] = None
            continue
        attempted = True
        resolved[market] = MarketCalendarAuthority.try_load_offline(calendar_id, data_root=data_root)
    return resolved, attempted


def import_incoming_files(
    run_id: str,
    incoming_directory: Path | None = None,
    filename_metadata: Mapping[str, Mapping[str, str]] | None = None,
    *,
    calendar_authority: MarketCalendarAuthority | None = None,
    lifecycle_evidence: Mapping[tuple[str, str | None], ContractLifecycleEvidence] | None = None,
    _before_target_claim: Callable[[Path], None] | None = None,
    _after_canonical_read: Callable[[Path, int], None] | None = None,
) -> list[Path]:
    """Import supported files independently, quarantining failures without stopping later files.

    §129.17 — after a successful fresh import, session-gap evidence for each
    canonical target is computed through the authoritative
    ``engine.market.calendar`` authority and recorded on the import manifest
    (``gaps_status``, ``gap_missing_candidate_count``, ``gap_known_closed_count``,
    ``gap_calendar_unavailable``, ``gap_samples``).  Gap analysis is read-only:
    canonical data is never rewritten, extended, or fabricated.  ALREADY_IMPORTED
    and quarantined outcomes carry no gap evidence (the publishing import owns it).

    ``calendar_authority`` allows explicit authority injection; when omitted,
    the deterministic offline dataset for the market tag is loaded from the
    local data root, and genuine local absence fails closed to
    CALENDAR_UNAVAILABLE evidence rather than any guess.
    ``lifecycle_evidence`` maps ``(instrument, expiry)`` to explicitly supplied
    contract-lifecycle evidence; without it, pre-listing/post-expiry states are
    never claimed.
    """
    report_paths: list[Path] = []
    metadata_by_file = filename_metadata or {}
    prior_manifests = _load_prior_import_manifests()
    if incoming_directory is None:
        from engine.data.feeds.data_root import data_path
        incoming_directory = data_path("incoming")

    # R2-B — run-local accepted fingerprint authority.
    # Initialized from prior accepted manifests; updated immediately after
    # each successful fresh import.  A quarantined/failed attempt must
    # NEVER enter this set.
    accepted_fingerprints: set[str] = {
        m.import_fingerprint
        for m in prior_manifests
        if m.status == "imported" and m.import_fingerprint is not None
    }

    with claim_import_run(run_id):
        for index, source_file in enumerate(discover_incoming_files(incoming_directory), start=1):
            report_id = f"{run_id}-{index}"
            source_format: str | None = None
            try:
                # §129.9 — immutable source evidence (before any processing)
                source_checksum, source_bytes = _compute_source_evidence(source_file)

                raw_data = read_source_file(source_file)
                # §129.14 — detect source format BEFORE normalization
                source_format = detect_source_format(raw_data)
                data = normalize_column_aliases(raw_data)
                parsed_metadata = parse_filename_metadata(source_file)
                supplied_metadata = metadata_by_file.get(source_file.name, {})
                for field, value in supplied_metadata.items():
                    if field in parsed_metadata and parsed_metadata[field] != value:
                        raise ValueError(f"Supplied filename metadata contradicts filename token for {field!r}.")
                    parsed_metadata[field] = value
                parsed_metadata["timeframe"] = resolve_timeframe(data, parsed_metadata)
                identities_and_data = detect_contract_identities(data, parsed_metadata)

                # §129.15 — resolve canonical target semantics for idempotency fingerprint.
                # Each element binds (canonical_output_path, resolved_source_timezone)
                # to capture timezone semantics that affect stored data but are
                # absent from the target path.
                canonical_target_semantics: tuple[tuple[str, str], ...] = tuple(
                    (str(resolve_storage_path(identity)), identity.source_timezone)
                    for identity, _ in identities_and_data
                )
                # Canonical output paths (for output_paths and supersession)
                canonical_targets: tuple[str, ...] = tuple(
                    path for path, _ in canonical_target_semantics
                )

                # §129.13 — compute import fingerprint
                import_fingerprint = _compute_fingerprint(
                    source_checksum_sha256=source_checksum,
                    canonical_target_semantics=canonical_target_semantics,
                )

                # R2-B — idempotency check (prior manifests OR same-run accepted)
                if import_fingerprint in accepted_fingerprints:
                    # R2-A — ALREADY_IMPORTED: deterministic observable no-op result.
                    # Zero canonical parquet rewrite.  Zero canonical_target_claim.
                    # The original IMPORTED manifest is the canonical evidence that
                    # the dataset was published; this manifest is execution evidence only.
                    # R3: output_paths records canonical target identity, NOT write count.
                    manifest = ImportManifest(
                        source_file=str(source_file),
                        status="already_imported",
                        detected_identity=None,
                        rows_read=len(data),
                        rows_accepted=0,
                        rows_rejected=0,
                        duplicates_removed=0,
                        output_paths=list(canonical_targets),
                        quarantine_reason=None,
                        source_checksum_sha256=source_checksum,
                        source_bytes=source_bytes,
                        import_fingerprint=import_fingerprint,
                    )
                    report_paths.append(write_import_manifest(manifest, report_id))
                    continue

                # §129.16 — supersession evidence
                prior_checksum = _find_supersession_prior(
                    prior_manifests, source_checksum, canonical_targets
                )

                # §129.17 — resolve the authoritative calendar evidence BEFORE
                # any canonical mutation.  A corrupt/unusable calendar file must
                # quarantine this source while canonical data stays untouched;
                # genuine local absence yields no authority (fail-closed
                # CALENDAR_UNAVAILABLE evidence) without blocking publication.
                from engine.data.feeds.gap_analysis import (
                    aggregate_gap_evidence,
                    analyze_target_gaps,
                )
                authority_by_market, _ = _resolve_gap_authority(
                    (identity.market for identity, _ in identities_and_data),
                    calendar_authority,
                )

                output_paths: list[Path] = []
                rows_accepted = rows_rejected = duplicates_removed = 0
                duplicate_conflicts = 0
                identities = []
                merged_frames: list[tuple[object, pd.Series]] = []

                for identity, contract_data in identities_and_data:
                    output_path = resolve_storage_path(identity)
                    if _before_target_claim is not None:
                        _before_target_claim(output_path)
                    # Cleaning, re-reading, merging, temporary writing, and
                    # replacement are one target-scoped critical section.
                    with canonical_target_claim(output_path, CANONICAL_STORAGE_ROOT):
                        cleaned_data, duplicates, rejected = clean_ohlcv(
                            contract_data,
                            duplicate_columns=["timestamp"],
                            timezone=identity.source_timezone,
                            instrument=identity.instrument,
                            timeframe=identity.timeframe,
                        )
                        merged_data, merge_duplicates, merge_rejected = _merge_with_existing_canonical_data(
                            cleaned_data, output_path, timezone=identity.source_timezone,
                            instrument=identity.instrument, timeframe=identity.timeframe,
                            on_existing_read=_after_canonical_read,
                        )
                        write_ohlcv_parquet(
                            merged_data, output_path, authorized_root=CANONICAL_STORAGE_ROOT,
                        )
                    identities.append(identity)
                    output_paths.append(output_path)
                    rows_accepted += len(cleaned_data)
                    rows_rejected += rejected + merge_rejected
                    duplicates_removed += duplicates + merge_duplicates
                    # §129.17 — retain published timestamps for read-only gap evidence.
                    if "timestamp" in merged_data.columns:
                        merged_frames.append((identity, merged_data["timestamp"]))

                    # §129.16 — duplicate conflict evidence
                    conflict_count = _compute_duplicate_conflicts(
                        contract_data, cleaned_data, output_path,
                        timezone=identity.source_timezone,
                        instrument=identity.instrument,
                        timeframe=identity.timeframe,
                    )
                    duplicate_conflicts += conflict_count

                # §129.17 — deterministic session-gap evidence through the
                # authoritative calendar/session abstraction (read-only).
                lifecycle_by_key = dict(lifecycle_evidence) if lifecycle_evidence else {}
                target_reports = [
                    analyze_target_gaps(
                        timestamps,
                        authority=authority_by_market.get(identity.market),
                        lifecycle=lifecycle_by_key.get((identity.instrument, identity.expiry)),
                        max_samples=_GAP_EVIDENCE_MAX_SAMPLES,
                    )
                    for identity, timestamps in merged_frames
                ]
                aggregate = aggregate_gap_evidence(target_reports, max_samples=_GAP_EVIDENCE_MAX_SAMPLES)

                # §129.13 — build manifest with provenance fields
                manifest = build_import_manifest(
                    source_file, identities, rows_read=len(data), rows_accepted=rows_accepted,
                    rows_rejected=rows_rejected, duplicates_removed=duplicates_removed,
                    output_paths=output_paths,
                )
                # Extend with provenance fields
                provenance_manifest = ImportManifest(
                    source_file=manifest.source_file,
                    status=manifest.status,
                    detected_identity=manifest.detected_identity,
                    rows_read=manifest.rows_read,
                    rows_accepted=manifest.rows_accepted,
                    rows_rejected=manifest.rows_rejected,
                    duplicates_removed=manifest.duplicates_removed,
                    output_paths=manifest.output_paths,
                    quarantine_reason=manifest.quarantine_reason,
                    source_checksum_sha256=source_checksum,
                    source_bytes=source_bytes,
                    import_fingerprint=import_fingerprint,
                    prior_source_checksum_sha256=prior_checksum,
                    duplicate_conflicts_removed=duplicate_conflicts,
                    source_format_version=source_format,
                    gaps_status=aggregate.gaps_status,
                    gap_missing_candidate_count=aggregate.missing_candidate_count,
                    gap_known_closed_count=aggregate.known_closed_count,
                    gap_calendar_unavailable=aggregate.calendar_unavailable,
                    gap_samples=list(aggregate.samples),
                )
                manifest = provenance_manifest

                # R2-B — update run-local accepted set immediately after fresh import
                accepted_fingerprints.add(import_fingerprint)

            except Exception as error:
                manifest = build_quarantine_manifest(source_file, str(error))
                # §129.14 — record format even on quarantine
                if source_format is not None:
                    from dataclasses import replace
                    manifest = replace(manifest, source_format_version=source_format)
            report_paths.append(write_import_manifest(manifest, report_id))
    return report_paths
