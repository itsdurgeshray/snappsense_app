import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SNAPPSENSE_LOCAL_MODEL", "")  # never call a local model in tests
