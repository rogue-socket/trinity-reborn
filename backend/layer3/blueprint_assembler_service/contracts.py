"""Pydantic schemas for persisted World Bible and Story Blueprint artifacts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BuildBlueprintRequest(BaseModel):
    # The identifier becomes a path segment, so it is parsed rather than trusted.
    topic_id: UUID


class EntityMapEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fictional_name: str = Field(min_length=1)
    fictional_type: Literal["institution", "place", "faction", "person"]
    description: str = Field(min_length=1)


class World(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: str = Field(min_length=1)
    world_id: UUID
    name: str = Field(min_length=1)
    entity_map: dict[str, EntityMapEntry]


class EmotionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: str = Field(min_length=1)
    secondary: str = Field(min_length=1)


class Character(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_entity_id: str | None
    role: Literal["protagonist", "supporting", "antagonist"]
    name: str = Field(min_length=1)
    goals: list[str]
    fears: list[str]
    personality: list[str]
    emotion_state: EmotionState


class BlueprintCharacter(Character):
    character_id: UUID


class TimelineEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    fictional_label: str
    order: int
    status: str
    participant_character_ids: list[str]
    epistemic_note: str


class DisputedThread(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    related_character_ids: list[str]
    use_as: Literal["plot tension, not resolved fact"]


class Blueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blueprint_id: UUID
    topic_id: str
    generated_at: datetime
    world: World
    characters: list[BlueprintCharacter]
    timeline: list[TimelineEntry]
    central_conflict: str
    themes: list[str]
    disputed_threads: list[DisputedThread]
    perspectives_to_generate: list[str]
    target_languages: list[Literal["en", "hi", "ta", "bn", "pa", "gu"]]

    @field_validator("target_languages")
    @classmethod
    def all_target_languages_are_present(cls, languages: list[str]) -> list[str]:
        expected = ["en", "hi", "ta", "bn", "pa", "gu"]
        if languages != expected:
            raise ValueError("target_languages must be en, hi, ta, bn, pa, gu in that order")
        return languages
