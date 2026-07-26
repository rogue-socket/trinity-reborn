"""Public Episode and internal model-output schemas."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateEpisodeRequest(BaseModel):
    # Both identifiers become path segments, so they are parsed rather than trusted.
    topic_id: UUID
    character_id: UUID
    force: bool = False


class Episode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: UUID
    blueprint_id: str
    topic_id: str
    character_id: str
    title: str
    status: Literal["story_generated", "translated", "audio_ready", "failed"]
    story_text: dict[str, str]
    audio: dict[str, Any]
    target_languages: list[str]
    created_at: datetime
    updated_at: datetime
    error: str | None
    translation_errors: dict[str, str] = Field(default_factory=dict)
    audio_errors: dict[str, str] = Field(default_factory=dict)
    voice_id: str | None = None


class GeneratedNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    story_text: str = Field(min_length=1)

    @field_validator("story_text")
    @classmethod
    def has_requested_length(cls, story_text: str) -> str:
        word_count = len(story_text.split())
        if not 500 <= word_count <= 800:
            raise ValueError("story_text must contain 500 to 800 words")
        return story_text
