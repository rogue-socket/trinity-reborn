"""Runtime settings for the Blueprint Assembler."""

import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")

LAYER2_BASE_URL = os.getenv("LAYER2_BASE_URL", "http://localhost:8000").rstrip("/")
WORLD_BIBLE_DIR = Path(os.getenv("WORLD_BIBLE_DIR", "./world_bible"))
BLUEPRINT_DIR = Path(os.getenv("BLUEPRINT_DIR", "./blueprints"))
