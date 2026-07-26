"""FastAPI entry point for ElevenLabs audio narration."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.layer3.story_generator_service.contracts import Episode

from .audio import AudioError, narrate, subscription_snapshot, validate_elevenlabs_key
from .contracts import NarrateRequest


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
