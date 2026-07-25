import sys
from pathlib import Path


# The Layer 3 services are top-level packages at the repository root, outside `backend`.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
