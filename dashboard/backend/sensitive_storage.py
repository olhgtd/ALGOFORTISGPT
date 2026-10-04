"""Fail-closed filesystem boundary for dedicated security SQLite stores.

The application must supply a validated production data root and, on Windows,
an installer/service-provided ACL validator.  This module deliberately does
not claim that inherited ACLs are secure.
"""
from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from typing import Literal, Protocol


StorageProfile = Literal["development", "test", "production", "local_private"]


class SensitiveStorageError(RuntimeError):
    pass


class WindowsAclValidator(Protocol):
    """Trusted installer/service authority for a restrictive Windows DACL."""

    def validate(self, data_root: Path) -> bool: ...


_STORE_LAYOUT = {
    "security": ("security", "algofortis_security.sqlite3"),
    "governance": ("governance", "algofortis_governance.sqlite3"),
}


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _chmod_owner_only(path: Path, mode: int) -> None:
    if os.name == "nt":
        return
    try:
        path.chmod(mode)
    except OSError as exc:
        raise SensitiveStorageError(f"could not set restrictive permissions on {path}") from exc
    if stat.S_IMODE(path.stat().st_mode) & ~mode:
        raise SensitiveStorageError(f"insecure permissions on {path}")


def resolve_sensitive_sqlite_path(
    path: Path,
    *,
    store: Literal["security", "governance"],
    profile: StorageProfile = "development",
    data_root: Path | None = None,
    windows_acl_validator: WindowsAclValidator | None = None,
) -> Path:
    """Resolve a dedicated-store path and enforce production filesystem rules."""
    candidate = Path(path).expanduser().resolve(strict=False)
    if profile not in {"development", "test", "production", "local_private"}:
        raise SensitiveStorageError("unknown sensitive-storage profile")
    if profile not in {"production", "local_private"}:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        return candidate

    if data_root is None:
        raise SensitiveStorageError("production sensitive storage requires an explicit data root")
    configured_root = Path(data_root).expanduser()
    if configured_root.exists() and configured_root.is_symlink():
        raise SensitiveStorageError("production sensitive data root cannot be a symlink or junction")
    root = configured_root.resolve(strict=False)
    source_root = _repository_root()
    temp_root = Path(tempfile.gettempdir()).resolve(strict=False)
    if _is_within(root, source_root):
        raise SensitiveStorageError("production sensitive data root cannot be inside the source tree")
    if _is_within(root, temp_root):
        raise SensitiveStorageError("production sensitive data root cannot be inside the temporary directory")
    directory_name, filename = _STORE_LAYOUT[store]
    expected = (root / directory_name / filename).resolve(strict=False)
    if candidate != expected or not _is_within(candidate, root):
        raise SensitiveStorageError("production sensitive database path must use the approved fixed store location")

    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise SensitiveStorageError("production sensitive data root cannot be a symlink or junction")
    expected.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        if windows_acl_validator is None or not windows_acl_validator.validate(root):
            raise SensitiveStorageError("production Windows data root requires trusted restrictive ACL validation")
    else:
        _chmod_owner_only(root, 0o700)
        _chmod_owner_only(expected.parent, 0o700)
    return expected


def harden_sensitive_sqlite_files(path: Path, *, profile: StorageProfile) -> None:
    """Apply POSIX owner-only permissions to database and existing WAL sidecars."""
    if profile not in {"production", "local_private"} or os.name == "nt":
        return
    for file_path in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        if file_path.exists():
            _chmod_owner_only(file_path, 0o600)
