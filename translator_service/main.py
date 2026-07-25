"""FastAPI entry point for Gemini episode translation."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from story_generator_service.contracts import Episode

from .contracts import TranslateRequest
from .translator import TranslatorError, translate_episode


app = FastAPI(title="translator_service", version="0.1.0")


@app.exception_handler(TranslatorError)
async def translator_error_handler(_: Request, exc: TranslatorError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.error, "message": exc.message})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/translate", response_model=Episode)
def translate(request: TranslateRequest) -> Episode:
    return translate_episode(request.topic_id, request.character_id, request.target_languages, request.force)
