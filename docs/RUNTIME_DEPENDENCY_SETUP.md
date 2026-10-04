# AlgoFortis runtime dependency setup

Supported verification runtime: CPython 3.13.14.

Create a clean environment and install the repository-controlled exact lock:

```powershell
# `py -3.13` selects a 3.13 interpreter; it does not pin patch version.
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe --version  # must print: Python 3.13.14
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.lock.txt
.\.venv\Scripts\python.exe -c "import yaml; print(yaml.__version__)"
.\.venv\Scripts\python.exe -m compileall -q engine strategies tests
.\.venv\Scripts\python.exe -m pytest -q
```

Do not treat a `py -3.13` selection as authoritative until the created
environment reports exactly `Python 3.13.14`.

`requirements-runtime.lock.txt` is the pip-consumable, exact approved runtime
closure. `requirements-runtime.lock.json` remains the machine-readable
reproducibility/evidence lock checked by the engine. `requirements-runtime.in`
declares the corresponding dependency names and is not an installer.

The isolated AutoClaw embedded Python is not a supported verification runtime:
it does not put the repository root on `sys.path` and ignores the subprocess
`PYTHONPATH` setup used by import-boundary tests. Do not add packaging or
`sys.path` workarounds solely for that environment.

### Phase 9 dashboard dependency boundary (docs-only note — NO dependencies installed)

The authoritative Phase 9 dashboard/control-surface contract (`BACKTEST_ENGINE_ARCHITECTURE_DECISIONS.md` §131)
mandates that Phase 9 dashboard dependencies (FastAPI backend; React + TypeScript
+ Vite frontend; optional UI/charting libraries) remain **isolated from the frozen
core AlgoFortis runtime dependency closure** where necessary. No Phase 9 dependency
is added, installed, or declared by this docs-only task. The core runtime closure
defined by `requirements-runtime.lock.txt` / `requirements-runtime.lock.json` is
**unchanged**. Exact Phase 9 dependency versions must be selected and frozen during
Phase 9 implementation (a `requirements-dashboard.txt` or equivalent will be created
then, not now) without destabilizing the existing AlgoFortis runtime.
