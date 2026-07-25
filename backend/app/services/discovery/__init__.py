"""Owned by: Research Engine Layer 1 team (Discovery, Extraction,
Deduplication, Package Building)."""

from app.services.discovery.service import GoogleNewsDiscoveryService
from app.services.discovery.workflow import DiscoveryWorkflow

__all__ = ["DiscoveryWorkflow", "GoogleNewsDiscoveryService"]
