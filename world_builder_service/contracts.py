"""Strict public and generated-data schemas."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator


class BuildWorldRequest(BaseModel):
    topic_id: str = Field(min_length=1)


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


class Characters(RootModel[dict[str, Character]]):
    @field_validator("root")
    @classmethod
    def character_ids_are_uuids(cls, values: dict[str, Character]) -> dict[str, Character]:
        for character_id in values:
            UUID(character_id)
        return values


class BuildWorldResponse(BaseModel):
    world: World
    characters: Characters


# Structured output returned by the model. Final IDs and roles remain service-owned.
class EntityMapDraft(EntityMapEntry):
    source_entity_id: str = Field(min_length=1)


class CharacterDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_entity_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    goals: list[str]
    fears: list[str]
    personality: list[str]
    emotion_state: EmotionState


class GenerationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    world_name: str = Field(min_length=1)
    entity_map: list[EntityMapDraft]
    characters: list[CharacterDraft]
