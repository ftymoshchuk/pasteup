import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# TestClient addresses every request to "testserver", which the app's Host check
# refuses by default. Set before any test module imports the app.
os.environ.setdefault("IMAGE_GRID_ALLOWED_HOSTS", "testserver")
