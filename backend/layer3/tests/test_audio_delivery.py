from uuid import uuid4

import pytest
from fastapi import HTTPException

import backend.layer3.audio_generator_service.main as audio_main


def test_audio_delivery_serves_a_persisted_mp3(tmp_path, monkeypatch) -> None:
    topic_id = uuid4()
    character_id = uuid4()
    audio_path = tmp_path / str(topic_id) / str(character_id) / "en.mp3"
    audio_path.parent.mkdir(parents=True)
    audio_path.write_bytes(b"fake-mp3")
    monkeypatch.setattr(audio_main, "AUDIO_DIR", tmp_path)

    response = audio_main.get_audio_file(topic_id, character_id, "en")

    assert response.path == audio_path
    assert response.media_type == "audio/mpeg"


def test_audio_delivery_rejects_missing_mp3(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(audio_main, "AUDIO_DIR", tmp_path)

    with pytest.raises(HTTPException) as error:
        audio_main.get_audio_file(uuid4(), uuid4(), "en")

    assert error.value.status_code == 404
