"""Runtime configuration for audio generation."""

from pathlib import Path

from dotenv import load_dotenv

from backend.shared.artifact_paths import artifact_dir


load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BLUEPRINT_DIR = artifact_dir("BLUEPRINT_DIR", "blueprints")
EPISODE_DIR = artifact_dir("EPISODE_DIR", "episodes")
AUDIO_DIR = artifact_dir("AUDIO_DIR", "audio")
OPENAI_MODEL = "gpt-5.6-sol"
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io"
