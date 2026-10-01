from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.portfolio.v2.evidence import render_g7_evidence


if __name__ == "__main__":
    sys.stdout.write(render_g7_evidence())
