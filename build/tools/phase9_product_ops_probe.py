from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard.backend.product_ops_v2.evidence import g9_markers


if __name__ == "__main__":
    for key, value in g9_markers():
        print(f"{key}={value}")
