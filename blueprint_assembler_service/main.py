"""FastAPI entry point for deterministic Story Blueprint assembly."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .assembler import BlueprintError, assemble_blueprint, write_blueprint
from .contracts import Blueprint, BuildBlueprintRequest


app = FastAPI(title="blueprint_assembler_service", version="0.1.0")


@app.exception_handler(BlueprintError)
async def blueprint_error_handler(_: Request, exc: BlueprintError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.error, "message": exc.message})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/build-blueprint", response_model=Blueprint)
def build_blueprint(request: BuildBlueprintRequest) -> Blueprint:
    try:
        blueprint = assemble_blueprint(str(request.topic_id))
    except BlueprintError:
        raise
    except (TypeError, ValueError) as exc:
        raise BlueprintError(
            500,
            "blueprint_validation_failed",
            "Blueprint inputs could not be assembled into the required schema; no file was written",
        ) from exc
    write_blueprint(blueprint)
    return blueprint
