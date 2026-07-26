"""FastAPI entry point for ElevenLabs audio narration."""

import logging
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException, Path, Request, status
from fastapi.responses import FileResponse, JSONResponse

from backend.layer3.story_generator_service.contracts import Episode

from .audio import AudioError, narrate, subscription_snapshot, validate_elevenlabs_key
from .config import AUDIO_DIR
from .contracts import NarrateRequest
from .final_demo import final_demo_audio_path, generate_final_demo_audio


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        validate_elevenlabs_key()
    except AudioError as exc:
        logger.fatal("Audio Generator cannot start: %s", exc.message)
        raise RuntimeError(exc.message) from exc
    yield


app = FastAPI(title="audio_generator_service", version="0.1.0", lifespan=lifespan)


@app.exception_handler(AudioError)
async def audio_error_handler(_: Request, exc: AudioError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.error, "message": exc.message})


@app.get("/health")
def health() -> dict[str, int | str | bool]:
    validate_elevenlabs_key()
    subscription = subscription_snapshot()
    return {
        "status": "ok",
        "elevenlabs_key_valid": True,
        "characters_used": subscription["character_count"],
        "character_limit": subscription["character_limit"],
    }


@app.post("/narrate", response_model=Episode)
def narrate_episode(request: NarrateRequest) -> Episode:
    return narrate(str(request.topic_id), str(request.character_id), request.languages, request.force)


@app.get("/audio/{topic_id}/{character_id}/{language}")
def get_audio_file(
    topic_id: UUID,
    character_id: UUID,
    language: str = Path(pattern=r"^[a-z]{2,12}(?:-[A-Za-z0-9]+)?$"),
) -> FileResponse:
    """Serve a generated narration file for the browser's native audio player."""
    audio_path = AUDIO_DIR / str(topic_id) / str(character_id) / f"{language}.mp3"
    if not audio_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generated audio was not found for this topic, character, and language",
        )
    return FileResponse(audio_path, media_type="audio/mpeg", filename=audio_path.name)


@app.post("/final-demo/audio/{story_id}")
def generate_final_demo_narration(story_id: str, force: bool = False) -> dict[str, str]:
    """Generate one curated final-demo narration with its intentionally fixed voice."""
    return generate_final_demo_audio(story_id, force)


@app.get("/final-demo/audio/{story_id}")
def get_final_demo_narration(story_id: str) -> FileResponse:
    audio_path = final_demo_audio_path(story_id)
    return FileResponse(audio_path, media_type="audio/mpeg", filename=audio_path.name)
