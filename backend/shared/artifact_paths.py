"""Resolve Layer 3 artefact directories relative to the repository root.

Env overrides may be absolute or repo-relative. Bare relative defaults used to resolve
against the process CWD, which broke the pipeline whenever a service was started from
another directory.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from threading import Lock


REPO_ROOT = Path(__file__).resolve().parents[2]
_replace_locks: dict[Path, Lock] = {}
_replace_locks_guard = Lock()


def artifact_dir(env_name: str, default_name: str) -> Path:
    configured = os.getenv(env_name)
    if not configured:
        return REPO_ROOT / default_name
    path = Path(configured).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def _replace_atomically(temporary_path: Path, destination: Path) -> None:
    """Serialize same-process replacements, which Windows rejects when concurrent."""
    resolved_destination = destination.resolve()
    with _replace_locks_guard:
        lock = _replace_locks.setdefault(resolved_destination, Lock())
    with lock:
        for attempt in range(4):
            try:
                temporary_path.replace(destination)
                return
            except PermissionError:
                if attempt == 3:
                    raise
                time.sleep(0.01 * (attempt + 1))


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Atomically replace a text artifact without sharing a temporary name.

    The temporary file must live beside the destination so ``replace`` remains
    atomic on the same filesystem. A unique name also makes simultaneous
    requests for the same artifact independent until the final replacement.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding=encoding) as temporary_file:
            temporary_file.write(content)
        _replace_atomically(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Atomically replace a binary artifact with a unique sibling temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(content)
        _replace_atomically(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
