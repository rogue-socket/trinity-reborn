"""Translator request schema; Episode is shared with story_generator_service."""

from uuid import UUID

from pydantic import BaseModel, field_validator


class TranslateRequest(BaseModel):
    # Both identifiers become path segments, so they are parsed rather than trusted.
    topic_id: UUID
    character_id: UUID
    target_languages: list[str] | None = None
    force: bool = False

    @field_validator("target_languages")
    @classmethod
    def target_languages_are_nonempty(cls, languages: list[str] | None) -> list[str] | None:
        if languages is not None and any(not language.strip() for language in languages):
            raise ValueError("target_languages cannot contain empty values")
        return languages
