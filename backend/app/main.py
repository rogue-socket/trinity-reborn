"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.discovery import router as discovery_router
from app.api.extraction import router as extraction_router

app = FastAPI(title="AI Research Engine", version="0.1.0")
app.include_router(discovery_router)
app.include_router(extraction_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "ok"}
