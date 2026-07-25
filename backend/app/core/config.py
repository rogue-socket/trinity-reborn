"""Application configuration."""

import os
from dataclasses import dataclass

DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://postgres:postgres@localhost:5432/current_affairs"
)


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    database_url: str


def get_settings() -> Settings:
    """Load application settings without coupling configuration to routes."""
    return Settings(database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
