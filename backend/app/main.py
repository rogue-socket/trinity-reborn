from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ingestions import router as ingestions_router
from app.api.layer1 import router as layer1_router
from app.api.retrieval import router as retrieval_router
from app.api.topics import router as topics_router
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
