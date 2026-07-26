from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.layer2.api.ingestions import router as ingestions_router
from backend.layer1.api import router as layer1_router
from backend.layer2.api.retrieval import router as retrieval_router
from backend.layer2.api.topics import router as topics_router
app = FastAPI(title="Trinity Reborn Layer 2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(topics_router)
app.include_router(ingestions_router)
app.include_router(retrieval_router)
app.include_router(layer1_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
