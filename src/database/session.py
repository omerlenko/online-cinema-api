from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
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
