"""Print deterministic G6 read-only evidence for cross-environment compare."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.live.phase6_evidence import build_g6_evidence, render_g6_evidence


def main() -> int:
    print(render_g6_evidence(build_g6_evidence()), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
