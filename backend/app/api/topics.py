import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Topic, TopicLifecycleTransition

router = APIRouter(tags=["topics"])


class TopicScope(BaseModel):
    description: str = Field(min_length=1)
    geography: list[str] = Field(default_factory=list)
    start: date
    end: date | None = None


class CreateTopicRequest(BaseModel):
    topic_key: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    display_name: str = Field(min_length=1, max_length=255)
    scope: TopicScope


class TopicResponse(BaseModel):
    topic_id: uuid.UUID
    topic_key: str
    status: str
    created_at: datetime


class TopicLifecycleRequest(BaseModel):
    status: str = Field(pattern="^(active|monitoring|closed|archived)$")
    reason: str = Field(min_length=1)


@router.get("/topics", response_model=list[TopicResponse])
def list_topics(session: Session = Depends(get_session)) -> list[TopicResponse]:
    return [
        TopicResponse(
            topic_id=topic.id,
            topic_key=topic.topic_key,
            status=topic.status,
            created_at=topic.created_at,
        )
        for topic in session.scalars(select(Topic).order_by(Topic.created_at.desc()))
    ]


@router.post("/topics", response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
def create_topic(payload: CreateTopicRequest, session: Session = Depends(get_session)) -> TopicResponse:
    topic = Topic(
        topic_key=payload.topic_key,
        display_name=payload.display_name,
        scope_json=payload.scope.model_dump(mode="json"),
    )
    session.add(topic)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(Topic.id).where(Topic.topic_key == payload.topic_key))
        if existing:
            raise HTTPException(status_code=409, detail="topic_key is already registered")
        raise
    session.refresh(topic)
    return TopicResponse(
        topic_id=topic.id,
        topic_key=topic.topic_key,
        status=topic.status,
        created_at=topic.created_at,
    )


@router.post("/topics/{topic_id}/lifecycle", response_model=TopicResponse)
def transition_topic(
    topic_id: uuid.UUID, payload: TopicLifecycleRequest, session: Session = Depends(get_session)
) -> TopicResponse:
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="unknown topic_id")
    if topic.status != payload.status:
        session.add(
            TopicLifecycleTransition(
                topic_id=topic.id,
                from_status=topic.status,
                to_status=payload.status,
                reason=payload.reason,
            )
        )
        topic.status = payload.status
        session.commit()
        session.refresh(topic)
    return TopicResponse(topic_id=topic.id, topic_key=topic.topic_key, status=topic.status, created_at=topic.created_at)
