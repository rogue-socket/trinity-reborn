import os
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@lru_cache
def get_engine():
    return create_engine(
        os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://trinity:trinity@localhost:5432/trinity_reborn",
        )
    )


def get_session() -> Generator[Session, None, None]:
    session = sessionmaker(bind=get_engine())()
    try:
        yield session
    finally:
        session.close()

