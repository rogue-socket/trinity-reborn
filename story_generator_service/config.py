"""Runtime settings for story generation."""

import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BLUEPRINT_DIR = Path(os.getenv("BLUEPRINT_DIR", "./blueprints"))
EPISODE_DIR = Path(os.getenv("EPISODE_DIR", "./episodes"))
OPENAI_MODEL = "gpt-5.6-sol"
