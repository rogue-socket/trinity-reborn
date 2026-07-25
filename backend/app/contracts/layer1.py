import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


SUPPORTED_SCHEMA_VERSION = "1.0"


class PackageMetadata(BaseModel):
    title: str = Field(min_length=1)
    generated_at: datetime


class Layer1Package(BaseModel):
    schema_version: str
    package_id: uuid.UUID
    topic_key: str = Field(min_length=1)
    metadata: PackageMetadata
    sources: list[dict[str, Any]]
    articles: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    events: list[dict[str, Any]]
    claims: list[dict[str, Any]]
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    uncertainties: list[dict[str, Any]] = Field(default_factory=list)
    themes: list[dict[str, Any]] = Field(default_factory=list)
    sentiment: list[dict[str, Any]] = Field(default_factory=list)

