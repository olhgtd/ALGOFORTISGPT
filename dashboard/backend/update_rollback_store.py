"""Integrity-checked retained rollback packages for AlgoFortis updates.

This store never executes a package. It only retains and verifies the previous
known-good installer bytes under the mutable per-user runtime cache so an
authorized update transaction can restore them after a failed upgrade.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dashboard.runtime.paths import check_no_symlink_or_reparse


_SCHEMA = "AlgoFortisUpdateRollbackArtifact/v1"
_SAFE_VERSION = re.compile(r"^[A-Za-z0-9._+-]{1,80}$")


@dataclass(frozen=True)
class RollbackArtifactRef:
    version: str
    sha256: str
    size_bytes: int
    package_path: Path
    metadata_path: Path


class UpdateRollbackStore:
    def __init__(self, runtime_root: Path, *, retain_count: int = 2):
        if retain_count < 1 or retain_count > 10:
            raise ValueError("retain_count must be between 1 and 10")
        self.root = Path(runtime_root).resolve() / "cache" / "updates" / "rollback"
        self.retain_count = retain_count

    def _prepare(self) -> None:
        check_no_symlink_or_reparse(self.root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        check_no_symlink_or_reparse(self.root)

    @staticmethod
    def _validate_version(version: str) -> str:
        value = str(version).strip()
        if not _SAFE_VERSION.fullmatch(value):
            raise ValueError("rollback version contains unsafe characters")
        return value

    def retain(self, *, version: str, installer_bytes: bytes) -> RollbackArtifactRef:
        version = self._validate_version(version)
        payload = bytes(installer_bytes)
        if not payload:
            raise ValueError("rollback package must not be empty")
        self._prepare()

        digest = hashlib.sha256(payload).hexdigest()
        package_path = self.root / f"AlgoFortis-Setup-{version}-{digest[:12]}.exe"
        metadata_path = package_path.with_suffix(".json")

        fd, temp_name = tempfile.mkstemp(prefix=".rollback-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, package_path)
        finally:
            Path(temp_name).unlink(missing_ok=True)

        metadata = {
            "schema": _SCHEMA,
            "version": version,
            "sha256": digest,
            "size_bytes": len(payload),
            "package_file": package_path.name,
        }
        fd, temp_meta = tempfile.mkstemp(prefix=".rollback-meta-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(metadata, handle, sort_keys=True, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_meta, metadata_path)
        finally:
            Path(temp_meta).unlink(missing_ok=True)

        self._prune()
        return RollbackArtifactRef(
            version=version,
            sha256=digest,
            size_bytes=len(payload),
            package_path=package_path,
            metadata_path=metadata_path,
        )

    def load_verified(self, ref: RollbackArtifactRef) -> bytes:
        self._prepare()
        package = Path(ref.package_path).resolve()
        metadata = Path(ref.metadata_path).resolve()
        if package.parent != self.root or metadata.parent != self.root:
            raise ValueError("rollback artifact escaped rollback root")
        check_no_symlink_or_reparse(package)
        check_no_symlink_or_reparse(metadata)

        data = json.loads(metadata.read_text(encoding="utf-8"))
        if data.get("schema") != _SCHEMA:
            raise ValueError("rollback metadata schema mismatch")
        if data.get("version") != ref.version:
            raise ValueError("rollback version mismatch")
        payload = package.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != ref.sha256 or digest != data.get("sha256"):
            raise ValueError("rollback package integrity mismatch")
        if len(payload) != ref.size_bytes or len(payload) != data.get("size_bytes"):
            raise ValueError("rollback package size mismatch")
        if data.get("package_file") != package.name:
            raise ValueError("rollback package metadata mismatch")
        return payload

    def _prune(self) -> None:
        packages = sorted(
            self.root.glob("AlgoFortis-Setup-*.exe"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for package in packages[self.retain_count :]:
            package.unlink(missing_ok=True)
            package.with_suffix(".json").unlink(missing_ok=True)
