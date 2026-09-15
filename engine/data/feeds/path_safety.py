"""Fail-closed filesystem boundaries for importer-owned destinations."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath


class PathSafetyError(ValueError):
    """Raised when externally derived path evidence is not one safe component."""


def require_safe_component(value: str, field_name: str) -> str:
    """Accept one literal path component without rewriting its identity."""
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise PathSafetyError(f"{field_name} must be a non-empty, trimmed path component")
    windows = PureWindowsPath(value)
    if (
        value in {".", ".."}
        or "/" in value
        or "\\" in value
        or Path(value).is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
    ):
        raise PathSafetyError(f"{field_name} is not a safe path component")
    return value


def path_within_root(root: Path, *components: str) -> Path:
    """Build a destination only when its resolved location stays under ``root``.

    Resolving existing ancestors also rejects an existing symlink/junction that
    already points outside the authorized root.  This is a containment check,
    not a normalization operation: supplied component text remains unchanged.
    """
    if not isinstance(root, Path):
        raise TypeError("root must be a Path")
    values = tuple(require_safe_component(value, "path component") for value in components)
    candidate = root.joinpath(*values)
    resolved_root = root.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as error:
        raise PathSafetyError("destination escapes its authorized storage root") from error
    return candidate


def assert_within_root(destination: Path, root: Path) -> None:
    """Re-check an existing destination before a filesystem mutation."""
    if not isinstance(destination, Path) or not isinstance(root, Path):
        raise TypeError("destination and root must be Path values")
    resolved_root = root.resolve(strict=False)
    resolved_destination = destination.resolve(strict=False)
    try:
        resolved_destination.relative_to(resolved_root)
    except ValueError as error:
        raise PathSafetyError("destination escapes its authorized storage root") from error
