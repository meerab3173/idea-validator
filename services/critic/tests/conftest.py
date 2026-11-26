import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))                 # service root -> `src`
sys.path.insert(0, str(HERE.parents[3] / "libs" / "common"))  # shared `common`
