"""Comprehensive Brand Migration Inventory & Classification Auditor for AlgoFortis."""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build/stage",
    "build/installer",
    "runtime/python",
}

EXCLUDE_EXTS = {
    ".ico", ".png", ".jpg", ".jpeg", ".pyd", ".dll", ".exe", ".parquet", ".zip", ".whl"
}

def scan_repository():
    findings = []
    
    for root, dirs, files in os.walk(ROOT):
        rel_root = Path(root).relative_to(ROOT)
        # Check if dir should be skipped
        if any(part in EXCLUDE_DIRS or str(rel_root).replace("\\", "/").startswith(part) for part in EXCLUDE_DIRS for rel_root_part in rel_root.parts):
            continue
        
        for file in files:
            file_path = Path(root) / file
            if file_path.suffix.lower() in EXCLUDE_EXTS:
                continue
            
            rel_file = file_path.relative_to(ROOT)
            rel_str = str(rel_file).replace("\\", "/")
            
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            
            lines = content.splitlines()
            for idx, line in enumerate(lines, 1):
                if re.search(r"sentinelx", line, re.IGNORECASE):
                    findings.append((rel_str, idx, line.strip()))
                    
    return findings

if __name__ == "__main__":
    findings = scan_repository()
    print(f"Total SentinelX occurrences found: {len(findings)}")
    
    user_visible = []
    internal_stable = []
    historical_audit = []
    compat_migration = []
    
    for rel_file, line_no, line in findings:
        # Check if documentation / historical
        if rel_file.endswith(".md") or rel_file.endswith(".txt") or "/docs/" in rel_file:
            historical_audit.append((rel_file, line_no, line))
        elif "paths.py" in rel_file and "SentinelX" in line:
            compat_migration.append((rel_file, line_no, line))
        elif "START_SENTINELX.pyw" in rel_file or "SentinelXLauncher.cs" in rel_file or "sentinelx_installer.iss" in rel_file:
            compat_migration.append((rel_file, line_no, line))
        elif any(k in line for k in ["sentinelx_security.sqlite3", "sentinelx_governance.sqlite3", "sentinelx-local", "sentinelx.com", "sentinelx-recovery.com", "sentinelx_theme", "sentinelx_strike_policy", "sentinelx_historical_backtests", "sentinelx-runtime", "x-sentinelx-bootstrap", "SENTINELX_TEST_ALLOW_INSECURE_ACL", "SENTINELX_ACL_TARGET", "SENTINELX_ACL_CREATE", "generatePrototypeSentinelxId", "sentinelxId", "sentinelx-id-input", "sentinelx-core-wrapper"]):
            internal_stable.append((rel_file, line_no, line))
        elif line.strip().startswith("#") or line.strip().startswith("//") or line.strip().startswith("/*") or line.strip().startswith("*"):
            historical_audit.append((rel_file, line_no, line))
        elif "package.json" in rel_file or "package-lock.json" in rel_file or "requirements" in rel_file:
            internal_stable.append((rel_file, line_no, line))
        else:
            # Check if this could be user visible
            user_visible.append((rel_file, line_no, line))
            
    print(f"\nBreakdown:")
    print(f"  A. USER_VISIBLE_RENAME: {len(user_visible)}")
    for f, l, content in user_visible:
        print(f"     [USER_VISIBLE] {f}:{l} -> {content}")
        
    print(f"  B. SAFE_PRODUCT_PATH_MIGRATION: {len(compat_migration)}")
    print(f"  C. INTERNAL_STABLE_ID: {len(internal_stable)}")
    print(f"  D. HISTORICAL/AUDIT: {len(historical_audit)}")
