import sys
from pathlib import Path


# The Layer 3 services and shared packages live below the repository-root backend package.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
