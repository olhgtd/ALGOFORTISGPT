"""AST-based authority firewall for AI/Laya code.

Replaces regex-only detection with a structural check that cannot be bypassed by
module-qualified calls, aliasing, relative imports or dynamic import helpers.

engine/ai/**            : STRICT allowlist. May import only the standard library
                          (minus dangerous modules) and engine.ai / engine.core /
                          engine.data / engine.reproducibility.
dashboard/backend/ai_control.py and dashboard/backend/owner_admin/** :
                          ADJACENT. May not touch broker, live, execution, order or
                          RiskGate-minting surfaces.

Both: no reference to ApprovedOrder / mint helpers, and no eval/exec/compile/
__import__/importlib.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

STRICT_ENGINE_ALLOWED = ("engine.ai", "engine.core", "engine.data", "engine.reproducibility")
DENIED_STDLIB = frozenset({
    "importlib", "subprocess", "ctypes", "socket", "ssl", "http", "ftplib", "smtplib",
    "pickle", "marshal", "shelve", "runpy", "imp", "multiprocessing", "sqlite3",
    "webbrowser", "telnetlib", "xmlrpc", "socketserver", "asyncio.subprocess",
})
DENIED_STDLIB_SUBMODULES = ("urllib.request", "urllib.error", "asyncio.subprocess")
ADJACENT_DENIED_PREFIXES = (
    "engine.broker_adapters", "engine.broker_contract", "engine.live", "engine.execution",
    "engine.orders", "engine.risk.gate_v2", "engine.protective", "engine.reconciliation",
)
FORBIDDEN_NAMES = frozenset({"ApprovedOrder", "_mint_approved_order", "mint_approved_order",
                             "create_approved_order", "issue_approved_order"})
FORBIDDEN_CALLS = frozenset({"__import__", "eval", "exec", "compile"})
STDLIB = frozenset(sys.stdlib_module_names)


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def _mode(rel: str) -> str | None:
    rel = _norm(rel).lower()
    if rel.startswith("engine/ai/"):
        return "strict"
    if rel == "dashboard/backend/ai_control.py" or rel.startswith("dashboard/backend/owner_admin/"):
        return "adjacent"
    return None


def _resolve_relative(rel: str, level: int, module: str | None) -> str:
    parts = _norm(rel)[:-3].split("/")
    pkg = parts[:-1]  # drop module name (also correct for __init__)
    if level > 1:
        pkg = pkg[: len(pkg) - (level - 1)]
    return ".".join(pkg + ([module] if module else []))


def _under(name: str, prefixes: tuple[str, ...]) -> bool:
    return any(name == p or name.startswith(p + ".") for p in prefixes)


def scan_source(rel_path: str, text: str) -> list[str]:
    mode = _mode(rel_path)
    if mode is None:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:  # fail closed
        return [f"{rel_path}: cannot parse ({exc.msg}); firewall fails closed"]

    out: list[str] = []

    def check_module(name: str, lineno: int) -> None:
        top = name.split(".")[0]
        if top == "dashboard" and mode == "strict":
            out.append(f"{rel_path}:{lineno}: engine/ai may not import dashboard code ({name})")
        elif top == "engine":
            if mode == "strict" and not _under(name, STRICT_ENGINE_ALLOWED):
                out.append(f"{rel_path}:{lineno}: import '{name}' is outside the AI allowlist {STRICT_ENGINE_ALLOWED}")
            if mode == "adjacent" and _under(name, ADJACENT_DENIED_PREFIXES):
                out.append(f"{rel_path}:{lineno}: import '{name}' reaches an execution/broker authority")
        elif top in STDLIB:
            if top in DENIED_STDLIB or _under(name, DENIED_STDLIB_SUBMODULES):
                if mode == "strict":
                    out.append(f"{rel_path}:{lineno}: stdlib module '{name}' is forbidden in AI code")
                elif top in {"importlib", "subprocess", "ctypes", "pickle", "marshal", "runpy"}:
                    out.append(f"{rel_path}:{lineno}: stdlib module '{name}' is forbidden")
        elif mode == "strict":
            out.append(f"{rel_path}:{lineno}: third-party import '{name}' is forbidden in engine/ai")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                check_module(alias.name, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = _resolve_relative(rel_path, node.level, node.module)
            if base:
                check_module(base, node.lineno)
                for alias in node.names:  # from engine import execution
                    if base in ("engine", "engine.risk", "engine.orders", "engine.core") or base.count(".") == 0:
                        check_module(f"{base}.{alias.name}", node.lineno)
            for alias in node.names:
                if alias.name in FORBIDDEN_NAMES:
                    out.append(f"{rel_path}:{node.lineno}: import of '{alias.name}' is forbidden")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            out.append(f"{rel_path}:{node.lineno}: reference to '{node.id}' is forbidden")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
            out.append(f"{rel_path}:{node.lineno}: reference to '.{node.attr}' is forbidden")
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in FORBIDDEN_CALLS:
                out.append(f"{rel_path}:{node.lineno}: call to '{fn.id}' is forbidden")
            if isinstance(fn, ast.Attribute) and fn.attr in {"import_module", "__import__"}:
                out.append(f"{rel_path}:{node.lineno}: dynamic import '{fn.attr}' is forbidden")
    return sorted(set(out))


def check_repository(root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    files = list((root / "engine" / "ai").rglob("*.py"))
    files += list((root / "dashboard" / "backend" / "owner_admin").rglob("*.py"))
    ctl = root / "dashboard" / "backend" / "ai_control.py"
    if ctl.exists():
        files.append(ctl)
    for path in sorted(set(files)):
        rel = path.relative_to(root).as_posix()
        failures.extend(scan_source(rel, path.read_text(encoding="utf-8")))
    return failures


def main() -> int:
    failures = check_repository()
    if failures:
        print("AI_IMPORT_ALLOWLIST=FAIL")
        for item in failures:
            print(f"- {item}")
        return 1
    print("AI_IMPORT_ALLOWLIST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
