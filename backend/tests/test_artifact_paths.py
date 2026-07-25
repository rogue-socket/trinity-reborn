"""Artefact directories must resolve against the repository root, not the process CWD."""


import artifact_paths


def test_default_artifact_dir_is_under_the_repo_root(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("WORLD_BIBLE_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    path = artifact_paths.artifact_dir("WORLD_BIBLE_DIR", "world_bible")
    assert path == artifact_paths.REPO_ROOT / "world_bible"
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
