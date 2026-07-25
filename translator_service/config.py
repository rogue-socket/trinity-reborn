"""Runtime settings for episode translation."""

import os
from pathlib import Path

from dotenv import load_dotenv

from artifact_paths import artifact_dir


load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BLUEPRINT_DIR = artifact_dir("BLUEPRINT_DIR", "blueprints")
EPISODE_DIR = artifact_dir("EPISODE_DIR", "episodes")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
