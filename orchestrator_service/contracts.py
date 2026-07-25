"""Request and report schemas for an orchestrated topic run."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RunTopicRequest(BaseModel):
    # Identifiers become path segments downstream, so they are parsed rather than trusted.
    topic_id: UUID
    character_ids: list[UUID] | None = None
    languages: list[str] | None = None
    narrate: bool = False

    @field_validator("languages")
    @classmethod
    def values_are_nonempty(cls, values: list[str] | None) -> list[str] | None:
        if values is not None and any(not value.strip() for value in values):
            raise ValueError("languages cannot contain empty values")
        return values


class CharacterRunOutcome(BaseModel):
    story_status: Literal["ok", "failed"]
    translation_status: Literal["ok", "partial", "failed"]
    translation_errors: dict[str, str] = Field(default_factory=dict)
    audio_status: Literal["ok", "partial", "failed", "skipped"]
    audio_errors: dict[str, str] = Field(default_factory=dict)


class RunReport(BaseModel):
    run_id: UUID
    topic_id: str
    narrate_requested: bool
    started_at: datetime
    finished_at: datetime
    world_status: Literal["ok", "failed"]
    blueprint_status: Literal["ok", "failed"]
    characters: dict[str, CharacterRunOutcome]
