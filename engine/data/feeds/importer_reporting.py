"""Import manifest and quarantine reporting for the historical-data importer."""

import json
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile

from engine.data.feeds.canonical_lock import canonical_target_claim
from engine.data.feeds.importer_identity import CanonicalIdentity
from engine.data.feeds.path_safety import assert_within_root, path_within_root, require_safe_component
from engine.data.feeds.data_root import data_path


IMPORT_REPORT_ROOT = data_path("import_reports")
RUN_CLAIM_DIRECTORY = ".run_claims"


@dataclass(frozen=True)
class ImportManifest:
    """Required, secret-free report for one importer source-file outcome.

    Phase 8.5 (§129.13) extends this canonical report additively with
    acquisition provenance fields.  All new fields carry defaults so every
    pre-existing constructor call site and serialized consumer stays valid.
    """

    source_file: str
    status: str
    detected_identity: dict[str, str | None] | list[dict[str, str | None]] | None
    rows_read: int
    rows_accepted: int
    rows_rejected: int
    duplicates_removed: int
    output_paths: list[str]
    quarantine_reason: str | None
    # ---- Phase 8.5 acquisition provenance (§129.13, all defaulted) ----
    contract_version: str = "sentinelx-acquisition/v1"
    parser_identity: str = "sentinelx.importer_orchestrator/v1"
    source_checksum_sha256: str | None = None
    source_bytes: int | None = None
    provider: str | None = None
    import_fingerprint: str | None = None
    prior_source_checksum_sha256: str | None = None
    observed_range_start: str | None = None
    observed_range_end: str | None = None
    duplicate_conflicts_removed: int = 0
    source_format_version: str | None = None
    gaps_status: str | None = None
    gap_missing_candidate_count: int = 0
    gap_known_closed_count: int = 0
    gap_calendar_unavailable: bool = False
    gap_samples: list[str] | None = None


def build_quarantine_manifest(source_file: Path, reason: str) -> ImportManifest:
    """Build the required report for a file that must not enter the Parquet store."""
    return ImportManifest(
        source_file=str(source_file),
        status="quarantined",
        detected_identity=None,
        rows_read=0,
        rows_accepted=0,
        rows_rejected=0,
        duplicates_removed=0,
        output_paths=[],
        quarantine_reason=reason,
    )


def build_import_manifest(
    source_file: Path,
    identities: list[CanonicalIdentity],
    rows_read: int,
    rows_accepted: int,
    rows_rejected: int,
    duplicates_removed: int,
    output_paths: list[Path],
) -> ImportManifest:
    """Build the required report for a successfully routed source file."""
    return ImportManifest(
        source_file=str(source_file),
        status="imported",
        detected_identity=[identity.as_dict() for identity in identities],
        rows_read=rows_read,
        rows_accepted=rows_accepted,
        rows_rejected=rows_rejected,
        duplicates_removed=duplicates_removed,
        output_paths=[str(path) for path in output_paths],
        quarantine_reason=None,
    )


def _parent_claim_path(run_id: str) -> Path:
    safe_run_id = require_safe_component(run_id, "run_id")
    digest = sha256(safe_run_id.encode("utf-8")).hexdigest()
    claim_directory = path_within_root(IMPORT_REPORT_ROOT, RUN_CLAIM_DIRECTORY)
    return path_within_root(claim_directory, f"{digest}.claim")


def _parent_commit_path(run_id: str) -> Path:
    safe_run_id = require_safe_component(run_id, "run_id")
    digest = sha256(safe_run_id.encode("utf-8")).hexdigest()
    claim_directory = path_within_root(IMPORT_REPORT_ROOT, RUN_CLAIM_DIRECTORY)
    return path_within_root(claim_directory, f"{digest}.committed")


def _has_committed_parent_run(run_id: str) -> bool:
    """Recognize the unambiguous parent commitment, never infer it from a child label."""
    return _parent_commit_path(run_id).is_file()


def _publish_parent_commit(run_id: str) -> None:
    """Atomically make one completed parent run ID permanently unavailable."""
    commit_path = _parent_commit_path(run_id)
    commit_path.parent.mkdir(parents=True, exist_ok=True)
    assert_within_root(commit_path, IMPORT_REPORT_ROOT)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(dir=commit_path.parent, suffix=".commit.tmp", delete=False) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(run_id.encode("utf-8"))
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        # Atomic create rather than replacement preserves the first commitment.
        os.link(temporary_path, commit_path)
    except FileExistsError as error:
        raise FileExistsError(f"authoritative importer run_id already committed: {run_id!r}") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


@contextmanager
def claim_import_run(run_id: str):
    """Exclusively claim one parent logical import run without reusing it."""
    run_id = require_safe_component(run_id, "run_id")
    claim_path = _parent_claim_path(run_id)
    with canonical_target_claim(claim_path, IMPORT_REPORT_ROOT):
        if _has_committed_parent_run(run_id):
            raise FileExistsError(f"authoritative importer run_id already committed: {run_id!r}")
        yield run_id
        _publish_parent_commit(run_id)


def write_import_manifest(manifest: ImportManifest, run_id: str) -> Path:
    """Atomically publish one child report only when its destination is unclaimed."""
    run_id = require_safe_component(run_id, "run_id")
    report_path = path_within_root(IMPORT_REPORT_ROOT, f"{run_id}.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    assert_within_root(report_path, IMPORT_REPORT_ROOT)
    payload = json.dumps(asdict(manifest), indent=2).encode("utf-8")
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(dir=report_path.parent, suffix=".json.tmp", delete=False) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        assert_within_root(report_path, IMPORT_REPORT_ROOT)
        # Hard-link publication is atomic and refuses an existing destination;
        # unlike os.replace, it cannot overwrite committed evidence.
        os.link(temporary_path, report_path)
    except FileExistsError as error:
        raise FileExistsError(f"authoritative import report already exists: {run_id!r}") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return report_path
