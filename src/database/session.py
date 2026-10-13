from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import get_settings

settings = get_settings()

postgresql_engine = create_async_engine(
    settings.POSTGRES_URL,
)
AsyncPostgresqlSession = async_sessionmaker(
    bind=postgresql_engine,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with AsyncPostgresqlSession() as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]


# Engine for code that runs outside the API's event loop (Celery tasks).
# Every task run gets a new event loop from asyncio.run(), and a pooled
# connection only works in the loop that opened it, so this engine keeps no pool.
task_engine = create_async_engine(settings.POSTGRES_URL, poolclass=NullPool)
TaskSession = async_sessionmaker(
    bind=task_engine,
    autoflush=False,
    expire_on_commit=False,
)
