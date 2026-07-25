"""Audio Generator request and OpenAI voice-profile response schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NarrateRequest(BaseModel):
    topic_id: str = Field(min_length=1)
    character_id: str = Field(min_length=1)
    languages: list[str] | None = None
    force: bool = False

    @field_validator("languages")
    @classmethod
    def languages_are_nonempty(cls, languages: list[str] | None) -> list[str] | None:
        if languages is not None and any(not language.strip() for language in languages):
            raise ValueError("languages cannot contain empty values")
        return languages


class VoiceInference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gender: Literal["male", "female", "neutral"]
    accent_or_region: str = Field(min_length=1)
    age_range: Literal["young_adult", "middle_aged", "older_adult"]


class VoiceProfile(VoiceInference):
    voice_id: str = Field(min_length=1)
