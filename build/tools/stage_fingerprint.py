"""Produce canonical pre-sign stage evidence for AlgoFortis release packaging."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


_SCHEMA = "AlgoFortisStageEvidence/v1"
_GENERATED_NONPORTABLE = frozenset({"AlgoFortis.exe"})


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint(rows: list[dict]) -> str:
    payload = json.dumps(
        rows,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_stage_evidence(stage: Path) -> dict:
    stage = stage.resolve()
    if not stage.is_dir():
        raise ValueError(f"stage directory does not exist: {stage}")

    rows: list[dict] = []
    for path in sorted((p for p in stage.rglob("*") if p.is_file()), key=lambda p: p.as_posix()):
        relative = path.relative_to(stage).as_posix()
        rows.append(
            {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": _sha(path),
            }
        )
    if not rows:
        raise ValueError("release stage is empty")

    by_path = {row["path"]: row for row in rows}
    for required in (
        "AlgoFortis.exe",
        "runtime/python/python.exe",
        "Microsoft.Web.WebView2.Core.dll",
        "Microsoft.Web.WebView2.WinForms.dll",
        "WebView2Loader.dll",
        "dashboard/web/dist/index.html",
    ):
        if required not in by_path:
            raise ValueError(f"required staged file is missing: {required}")

    portable_rows = [
        row for row in rows
        if row["path"] not in _GENERATED_NONPORTABLE
    ]
    generated_rows = [
        row for row in rows
        if row["path"] in _GENERATED_NONPORTABLE
    ]

    return {
        "schema": _SCHEMA,
        "file_count": len(rows),
        "all_files_fingerprint_sha256": _fingerprint(rows),
        "reproducible_payload_fingerprint_sha256": _fingerprint(portable_rows),
        "reproducible_payload_excludes": sorted(_GENERATED_NONPORTABLE),
        "generated_binary_evidence": generated_rows,
        "files": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    evidence = build_stage_evidence(Path(args.stage))
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print("STAGE_EVIDENCE=PASS")
    print(f"STAGE_FILE_COUNT={evidence['file_count']}")
    print(
        "REPRODUCIBLE_PAYLOAD_FINGERPRINT="
        + evidence["reproducible_payload_fingerprint_sha256"]
    )
    print("ALL_FILES_FINGERPRINT=" + evidence["all_files_fingerprint_sha256"])


if __name__ == "__main__":
    main()
