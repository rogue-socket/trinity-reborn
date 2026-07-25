"""Resolve Layer 3 artefact directories relative to the repository root.

Env overrides may be absolute or repo-relative. Bare relative defaults used to resolve
against the process CWD, which broke the pipeline whenever a service was started from
another directory.
"""

from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent


def artifact_dir(env_name: str, default_name: str) -> Path:
    configured = os.getenv(env_name)
    if not configured:
        return REPO_ROOT / default_name
    path = Path(configured).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path
