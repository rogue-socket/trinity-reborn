"""Runtime settings for the Blueprint Assembler."""

import os
from pathlib import Path

from dotenv import load_dotenv

from backend.shared.artifact_paths import artifact_dir


load_dotenv(Path(__file__).resolve().parents[3] / ".env")

LAYER2_BASE_URL = os.getenv("LAYER2_BASE_URL", "http://localhost:8000").rstrip("/")
WORLD_BIBLE_DIR = artifact_dir("WORLD_BIBLE_DIR", "world_bible")
BLUEPRINT_DIR = artifact_dir("BLUEPRINT_DIR", "blueprints")
