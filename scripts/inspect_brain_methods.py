import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from friday_ui.core.engine import FridayBrain
print("FridayBrain methods:")
for m in sorted([m for m in dir(FridayBrain) if not m.startswith("__")]):
    print(f"  {m}")
