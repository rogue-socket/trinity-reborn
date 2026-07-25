"""FastAPI entry point for the Echoes workflow orchestrator."""

from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import AUDIO_URL, BLUEPRINT_URL, LAYER2_BASE_URL, STORY_GEN_URL, TRANSLATOR_URL, WORLD_BUILDER_URL
from .contracts import RunReport, RunTopicRequest
from .orchestrator import OrchestratorError, run_topic


app = FastAPI(title="orchestrator_service", version="0.1.0")


@app.exception_handler(OrchestratorError)
async def orchestrator_error_handler(_: Request, exc: OrchestratorError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.error, "message": exc.message})


@app.get("/health")
def health() -> dict[str, object]:
    services = {
        "layer2": LAYER2_BASE_URL,
        "world_builder": WORLD_BUILDER_URL,
        "blueprint_assembler": BLUEPRINT_URL,
        "story_generator": STORY_GEN_URL,
        "translator": TRANSLATOR_URL,
        "audio_generator": AUDIO_URL,
    }

    def check(name: str, base_url: str) -> tuple[str, bool]:
        try:
            response = httpx.get(f"{base_url}/health", timeout=10.0)
            return name, response.is_success
        except httpx.HTTPError:
            return name, False

    reachable: dict[str, dict[str, bool]] = {}
    with ThreadPoolExecutor(max_workers=len(services)) as executor:
        futures = [executor.submit(check, name, url) for name, url in services.items()]
        for future in as_completed(futures):
            name, is_reachable = future.result()
            reachable[name] = {"reachable": is_reachable}
    return {"status": "ok", "services": reachable}


@app.post("/run-topic", response_model=RunReport)
def run_topic_endpoint(request: RunTopicRequest) -> RunReport:
    return run_topic(request.topic_id, request.character_ids, request.languages, request.narrate)
