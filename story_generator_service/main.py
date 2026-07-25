"""FastAPI entry point for character-perspective episode generation."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .contracts import CreateEpisodeRequest, Episode
from .generator import EpisodeError, GenerationFailed, create_episode


app = FastAPI(title="story_generator_service", version="0.1.0")


@app.exception_handler(GenerationFailed)
async def generation_failed_handler(_: Request, exc: GenerationFailed) -> JSONResponse:
    return JSONResponse(status_code=502, content=exc.episode.model_dump(mode="json"))


@app.exception_handler(EpisodeError)
async def episode_error_handler(_: Request, exc: EpisodeError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.error, "message": exc.message})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/episodes", response_model=Episode)
def create_episode_endpoint(request: CreateEpisodeRequest) -> Episode:
    return create_episode(request.topic_id, request.character_id, request.force)
