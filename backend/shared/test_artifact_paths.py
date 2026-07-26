"""Artefact directories must resolve against the repository root, not the process CWD."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend.shared import artifact_paths


def test_default_artifact_dir_is_under_the_repo_root(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("WORLD_BIBLE_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    path = artifact_paths.artifact_dir("WORLD_BIBLE_DIR", "world_bible")
    assert artifact_paths.REPO_ROOT == Path(__file__).resolve().parents[2]
    assert path == Path(__file__).resolve().parents[2] / "world_bible"
    assert path.is_absolute()


def test_relative_env_override_is_anchored_to_the_repo_root(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BLUEPRINT_DIR", "./custom-blueprints")
    monkeypatch.chdir(tmp_path)
    path = artifact_paths.artifact_dir("BLUEPRINT_DIR", "blueprints")
    assert path == artifact_paths.REPO_ROOT / "./custom-blueprints"


def test_absolute_env_override_is_preserved(monkeypatch, tmp_path) -> None:
    absolute = tmp_path / "elsewhere"
    monkeypatch.setenv("AUDIO_DIR", str(absolute))
    assert artifact_paths.artifact_dir("AUDIO_DIR", "audio") == absolute


def test_atomic_writers_use_independent_temporary_files(tmp_path) -> None:
    destination = tmp_path / "shared.json"
    values = [f"value-{index}" for index in range(20)]

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda value: artifact_paths.atomic_write_text(destination, value), values))

    assert destination.read_text(encoding="utf-8") in values
    assert not list(tmp_path.glob("*.tmp"))
