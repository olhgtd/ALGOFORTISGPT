from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from engine.ai.v2.evidence import build_g8_evidence

if __name__=='__main__':
    print(build_g8_evidence().text(),end='')
