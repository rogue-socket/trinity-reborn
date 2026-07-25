"""Persistence models for discovery requests and RSS results."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class DiscoveryRequest(Base):
    """A request to retrieve the Google News RSS feed."""

    __tablename__ = "discovery_requests"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    results: Mapped[list["DiscoveryResult"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class DiscoveryResult(Base):
    """One normalized article returned for a discovery request."""

    __tablename__ = "discovered_articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    discovery_request_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("discovery_requests.id", ondelete="CASCADE"),
        index=True,
    )
    headline: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str] = mapped_column(String(255))
    published_date: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(Text)
    request: Mapped[DiscoveryRequest] = relationship(back_populates="results")
