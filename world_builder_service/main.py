"""FastAPI entry point for Echoes' world-building service."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .contracts import BuildWorldRequest, BuildWorldResponse
from .world_builder import WorldBuilderError, build_world


app = FastAPI(title="world_builder_service", version="0.1.0")


@app.exception_handler(WorldBuilderError)
async def world_builder_error_handler(_: Request, exc: WorldBuilderError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.error, "message": exc.message})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/build-world", response_model=BuildWorldResponse)
def build_world_endpoint(request: BuildWorldRequest) -> BuildWorldResponse:
    return build_world(request.topic_id)
