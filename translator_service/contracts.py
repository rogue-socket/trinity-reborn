"""Translator request schema; Episode is shared with story_generator_service."""

from pydantic import BaseModel, Field, field_validator


class TranslateRequest(BaseModel):
    topic_id: str = Field(min_length=1)
    character_id: str = Field(min_length=1)
    target_languages: list[str] | None = None
    force: bool = False

    @field_validator("target_languages")
    @classmethod
    def target_languages_are_nonempty(cls, languages: list[str] | None) -> list[str] | None:
        if languages is not None and any(not language.strip() for language in languages):
            raise ValueError("target_languages cannot contain empty values")
        return languages
