"""Regression verification harness ensuring product modules resolve to the clean repository root."""
import os
import sys
import subprocess
from pathlib import Path

clean_root = Path(__file__).resolve().parents[2]
clean_root_posix = clean_root.as_posix()

def main():
    print("=== STARTING REGRESSION VERIFICATION ===")
    assert clean_root.exists(), f"Clean root missing: {clean_root}"

    # Verify import resolution
    verify_script = f"""
import sys
from pathlib import Path
sys.path.insert(0, '{clean_root_posix}')

import dashboard
import dashboard.runtime.controller
import dashboard.runtime.paths
import dashboard.backend.api

dash_path = Path(dashboard.__file__).resolve().as_posix()
clean_path = Path('{clean_root_posix}').resolve().as_posix()

print("dashboard resolves to:", dash_path)
assert dash_path.startswith(clean_path), "Import pollution! Expected prefix " + clean_path + ", got " + dash_path
print("IMPORT_RESOLUTION_PASS: dashboard originates strictly from clean repository root")
"""
    py_stage = clean_root / "build" / "stage" / "runtime" / "python" / "python.exe"
    py_exec = str(py_stage) if py_stage.exists() else sys.executable
    res = subprocess.run([py_exec, "-c", verify_script], capture_output=True, text=True)
    print(res.stdout)
    if res.returncode != 0:
        print("Import check error:", res.stderr)
        sys.exit(1)

    # Run primary architectural foundation test suite
    foundation_tests = clean_root / "tests_v1" / "test_architectural_foundations.py"
    print(f"Executing self-contained architectural tests from {foundation_tests.name}...")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(clean_root)
    env["SENTINELX_TEST_ALLOW_INSECURE_ACL"] = "1"
    env["ALGOFORTIS_TEST_ALLOW_INSECURE_ACL"] = "1"

    test_res = subprocess.run([sys.executable, "-m", "unittest", str(foundation_tests)],
                              cwd=str(clean_root), env=env, capture_output=True, text=True)
    print(test_res.stdout)
    if test_res.stderr:
        print(test_res.stderr)
    assert test_res.returncode == 0, f"Foundations test failed with exit code {test_res.returncode}"

    # Optional reference check if external migration repo exists
    ref_repo_env = os.environ.get("SENTINELX_REF_REPO", "").strip()
    ref_test = Path(ref_repo_env) / "tests" / "test_step7_runtime.py" if ref_repo_env else None
    if ref_test is not None and ref_test.exists():
        print(f"Executing optional reference test {ref_test.name}...")
        pytest_res = subprocess.run(["pytest", str(ref_test), "-v"], cwd=str(clean_root), env=env, capture_output=True, text=True)
        print(pytest_res.stdout)
        if pytest_res.returncode == 0:
            print("Reference test passed.")

    print("=== REGRESSION VERIFICATION: ALL PASS ===")

if __name__ == "__main__":
    main()
