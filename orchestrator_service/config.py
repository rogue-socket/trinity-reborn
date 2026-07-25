"""Runtime configuration for the Echoes service orchestrator."""

import os
from pathlib import Path

from dotenv import load_dotenv

from artifact_paths import artifact_dir


load_dotenv(Path(__file__).resolve().parents[1] / ".env")

LAYER2_BASE_URL = os.getenv("LAYER2_BASE_URL", "http://localhost:8000").rstrip("/")
WORLD_BUILDER_URL = os.getenv("WORLD_BUILDER_URL", "http://localhost:8001").rstrip("/")
BLUEPRINT_URL = os.getenv("BLUEPRINT_URL", "http://localhost:8002").rstrip("/")
STORY_GEN_URL = os.getenv("STORY_GEN_URL", "http://localhost:8003").rstrip("/")
TRANSLATOR_URL = os.getenv("TRANSLATOR_URL", "http://localhost:8004").rstrip("/")
AUDIO_URL = os.getenv("AUDIO_URL", "http://localhost:8005").rstrip("/")
RUN_HISTORY_DIR = artifact_dir("RUN_HISTORY_DIR", "runs")

# LLM and audio generation may take appreciably longer than ordinary HTTP handlers.
DOWNSTREAM_TIMEOUT_SECONDS = float(os.getenv("DOWNSTREAM_TIMEOUT_SECONDS", "180"))
DEMO_MODE = os.getenv("DEMO_MODE", "").strip().casefold() in {"1", "true", "yes", "on"}
