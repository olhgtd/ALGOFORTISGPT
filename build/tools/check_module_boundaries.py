"""Static import-boundary checks for AlgoFortis V2.

Implements the first enforceable AF2-OPS-002 architecture rules without adding a
runtime dependency.  The checker uses Python's AST, so imports are inspected
without importing or executing repository modules.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


DOMAIN_ROOTS = frozenset(
    {
        "core",
        "market",
        "options",
        "orders",
        "portfolio",
        "risk",
        "strategy",
    }
)

ADAPTER_PREFIXES = (
    "engine.broker_adapters",
)

TRANSPORT_PREFIXES = (
    "dashboard",
)

LIVE_ADAPTER_PREFIXES = (
    "engine.broker_adapters.angel_adapter",
    "engine.broker_adapters.dhan_adapter",
    "engine.broker_adapters.kite_adapter",
    "engine.broker_adapters.upstox_adapter",
    "engine.broker_adapters.factory",
)

IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
    }
)


@dataclass(frozen=True, slots=True)
class BoundaryViolation:
    path: str
    line: int
    code: str
    imported: str
    message: str

    def render(self) -> str:
        imported = f" [{self.imported}]" if self.imported else ""
        return f"{self.path}:{self.line}: {self.code}: {self.message}{imported}"


def _normalized_path(path: str) -> PurePosixPath:
    return PurePosixPath(str(path).replace("\\", "/"))


def _is_prefix(module: str, prefixes: Iterable[str]) -> bool:
    return any(module == prefix or module.startswith(prefix + ".") for prefix in prefixes)


def _import_names(tree: ast.AST) -> Iterable[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            # Relative imports stay within their package unless they explicitly name
            # an absolute target; boundary checks operate on absolute package names.
            if node.level == 0 and node.module:
                yield node.lineno, node.module


def _engine_area(path: PurePosixPath) -> str | None:
    parts = path.parts
    try:
        index = parts.index("engine")
    except ValueError:
        return None
    if index + 1 >= len(parts):
        return None
    return parts[index + 1]


def check_source_text(path: str, source: str) -> list[BoundaryViolation]:
    """Return import-boundary violations for one Python source string."""

    normalized = _normalized_path(path)
    display_path = normalized.as_posix()
    try:
        tree = ast.parse(source, filename=display_path)
    except SyntaxError as exc:
        return [
            BoundaryViolation(
                path=display_path,
                line=exc.lineno or 1,
                code="AF2-OPS-002-SYNTAX",
                imported="",
                message="source could not be parsed; boundary verification fails closed",
            )
        ]

    area = _engine_area(normalized)
    violations: list[BoundaryViolation] = []

    for line, imported in _import_names(tree):
        if area in DOMAIN_ROOTS:
            if _is_prefix(imported, ADAPTER_PREFIXES):
                violations.append(
                    BoundaryViolation(
                        path=display_path,
                        line=line,
                        code="AF2-OPS-002-DOMAIN-ADAPTER",
                        imported=imported,
                        message="domain code must not import adapter implementations",
                    )
                )
            if _is_prefix(imported, TRANSPORT_PREFIXES):
                violations.append(
                    BoundaryViolation(
                        path=display_path,
                        line=line,
                        code="AF2-OPS-002-DOMAIN-TRANSPORT",
                        imported=imported,
                        message="domain code must not import UI/transport modules",
                    )
                )

        if area in {"backtest", "paper"} and _is_prefix(imported, LIVE_ADAPTER_PREFIXES):
            violations.append(
                BoundaryViolation(
                    path=display_path,
                    line=line,
                    code="AF2-OPS-002-MODE-ISOLATION",
                    imported=imported,
                    message=f"{area.upper()} code must not import live broker implementations",
                )
            )

    return violations


def _python_files(root: Path) -> Iterable[Path]:
    engine_root = root / "engine"
    if not engine_root.is_dir():
        raise FileNotFoundError(f"engine directory not found under repository root: {root}")

    for path in sorted(engine_root.rglob("*.py")):
        if any(part in IGNORED_DIRECTORY_NAMES for part in path.parts):
            continue
        yield path


def check_repository(root: Path) -> list[BoundaryViolation]:
    """Scan the repository's engine Python sources using the frozen Phase-1 rules."""

    repository_root = Path(root).resolve()
    violations: list[BoundaryViolation] = []
    for path in _python_files(repository_root):
        relative = path.relative_to(repository_root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            violations.append(
                BoundaryViolation(
                    path=relative,
                    line=1,
                    code="AF2-OPS-002-READ",
                    imported="",
                    message=f"source could not be read; boundary verification fails closed: {exc}",
                )
            )
            continue
        violations.extend(check_source_text(relative, source))
    return violations


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) > 1:
        print("usage: python build/tools/check_module_boundaries.py [REPOSITORY_ROOT]", file=sys.stderr)
        return 2

    root = Path(args[0] if args else ".")
    try:
        violations = check_repository(root)
    except (OSError, ValueError) as exc:
        print(f"AF2-OPS-002-CHECKER: {exc}", file=sys.stderr)
        return 2

    if violations:
        for violation in violations:
            print(violation.render(), file=sys.stderr)
        print(f"MODULE_BOUNDARY_FAIL: {len(violations)} violation(s)", file=sys.stderr)
        return 1

    print("MODULE_BOUNDARY_PASS: no enforced boundary violations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
