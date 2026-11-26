import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for p in (str(ROOT), str(ROOT / "apps" / "worker" / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)
