"""SourceIdentityPolicy/v1 content capture with fail-closed filesystem rules."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

from engine.reproducibility.codec import CanonicalCodec


def _canonical_path(project_root: Path, path: Path) -> str:
    relative = path.relative_to(project_root)
    text = PurePosixPath(relative.as_posix()).as_posix()
    if text.startswith("/") or text == "." or ".." in PurePosixPath(text).parts:
        raise ValueError("source path must be a project-relative non-traversing path")
    return text


@dataclass(frozen=True)
class SourceFileIdentity:
    relative_path: str
    content_fingerprint: str


@dataclass(frozen=True)
class SourceIdentity:
    policy_version: str
    files: tuple[SourceFileIdentity, ...]

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-source-identity/v1",
            (("policy_version", self.policy_version), ("files", tuple((item.relative_path, item.content_fingerprint) for item in self.files))),
        )


@dataclass(frozen=True)
class SourceIdentityPolicy:
    """Frozen source roots; non-Python runtime resources are allowlist-only."""

    version: str = "SourceIdentityPolicy/v1"
    python_roots: tuple[str, ...] = ("engine", "strategies")
    runtime_resources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        roots = tuple(self.python_roots)
        if roots != ("engine", "strategies"):
            raise ValueError("SourceIdentityPolicy/v1 has frozen Python roots engine and strategies")
        resources = tuple(sorted(PurePosixPath(item).as_posix() for item in self.runtime_resources))
        if len(resources) != len(set(resources)) or any(item.startswith("/") or ".." in PurePosixPath(item).parts for item in resources):
            raise ValueError("runtime resource allowlist must contain unique project-relative paths")
        object.__setattr__(self, "runtime_resources", resources)

    def capture(self, project_root: Path) -> SourceIdentity:
        root = Path(project_root).resolve()
        paths: list[Path] = []
        for root_name in self.python_roots:
            source_root = root / root_name
            if not source_root.is_dir():
                raise ValueError(f"required source root missing: {root_name}")
            root_attributes = getattr(source_root.stat(), "st_file_attributes", 0)
            if source_root.is_symlink() or root_attributes & 0x400:
                raise ValueError("source symlinks/reparse points are not certifiable under v1")
            paths.extend(path for path in source_root.rglob("*.py") if "__pycache__" not in path.parts)
        paths.extend(root / resource for resource in self.runtime_resources)
        records = tuple(self._read_file(root, path) for path in paths)
        ordered = tuple(sorted(records, key=lambda item: item.relative_path))
        if len({item.relative_path for item in ordered}) != len(ordered):
            raise ValueError("duplicate canonical source path")
        return SourceIdentity(self.version, ordered)

    @staticmethod
    def _read_file(project_root: Path, path: Path) -> SourceFileIdentity:
        if not path.is_file():
            raise ValueError(f"declared source/resource file missing: {path}")
        stat_before = path.stat()
        attributes = getattr(stat_before, "st_file_attributes", 0)
        if path.is_symlink() or attributes & 0x400:  # Windows FILE_ATTRIBUTE_REPARSE_POINT
            raise ValueError("source symlinks/reparse points are not certifiable under v1")
        content = path.read_bytes()
        stat_after = path.stat()
        if (stat_before.st_size, stat_before.st_mtime_ns) != (stat_after.st_size, stat_after.st_mtime_ns):
            raise ValueError("source mutation detected during identity capture")
        relative = _canonical_path(project_root, path)
        content_fingerprint = CanonicalCodec.fingerprint(
            "algofortis-source-file/v1", (("path", relative), ("content", content))
        )
        return SourceFileIdentity(relative, content_fingerprint)

    @staticmethod
    def compose(policy_version: str, files: Iterable[SourceFileIdentity]) -> SourceIdentity:
        values = tuple(sorted(files, key=lambda item: item.relative_path))
        if not all(isinstance(item, SourceFileIdentity) for item in values):
            raise TypeError("files must contain SourceFileIdentity values")
        if len({item.relative_path for item in values}) != len(values):
            raise ValueError("duplicate canonical source path")
        return SourceIdentity(policy_version, values)
