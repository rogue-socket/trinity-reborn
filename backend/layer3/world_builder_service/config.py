"""Runtime settings for the world builder."""

import os
from pathlib import Path

from dotenv import load_dotenv

from backend.shared.artifact_paths import artifact_dir


# Load the repository's local development configuration before reading settings.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

LAYER2_BASE_URL = os.getenv("LAYER2_BASE_URL", "http://localhost:8000").rstrip("/")
WORLD_BIBLE_DIR = artifact_dir("WORLD_BIBLE_DIR", "world_bible")
OPENAI_MODEL = "gpt-5.6-sol"
