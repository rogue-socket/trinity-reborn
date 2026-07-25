"""Domain model definitions."""

from app.models.base import Base
from app.models.discovery import DiscoveryRequest, DiscoveryResult

__all__ = ["Base", "DiscoveryRequest", "DiscoveryResult"]
