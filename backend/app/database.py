"""PostgreSQL database connection and session configuration."""

from __future__ import annotations

import psycopg
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

engine = create_async_engine(settings.database_url, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def get_sync_connection() -> psycopg.Connection:
    """Return a synchronous psycopg connection for scripts and migrations."""
    url = make_url(settings.database_url)
    return psycopg.connect(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
        sslmode=url.query.get("sslmode", "require"),
    )
