from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text, insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from src.accounts.models import UserGroup, UserGroupEnum
from src.core.mailer import get_email_sender
from src.core.config import get_settings
from src.database.base import Base
from src.database.session import get_db
from src.main import app

settings = get_settings()
TEST_DB_NAME = f"{settings.POSTGRES_DB}_test"
TEST_DB_URL = settings.POSTGRES_URL.set(database=TEST_DB_NAME)


async def create_test_database() -> None:
    """Create the test database if it doesn't exist yet."""
    # CREATE DATABASE can't run inside a transaction, so connect to the
    # built-in "postgres" database in autocommit mode.
    admin_engine = create_async_engine(
        settings.POSTGRES_URL.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
    )
    async with admin_engine.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_DB_NAME},
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    await admin_engine.dispose()


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    await create_test_database()
    test_engine = create_async_engine(TEST_DB_URL)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(insert(UserGroup), [{"name": g} for g in UserGroupEnum])
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
async def db_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            autoflush=False,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@dataclass
class SentEmail:
    to: str
    subject: str
    body: str


class FakeEmailSender:

    def __init__(self) -> None:
        self.sent_emails: list[SentEmail] = []

    def send_email(self, to: str, subject: str, body: str) -> None:
        email = SentEmail(to, subject, body)
        self.sent_emails.append(email)


@pytest.fixture
def fake_email_sender(monkeypatch):
    fake = FakeEmailSender()
    monkeypatch.setitem(
        app.dependency_overrides,
        get_email_sender,
        lambda: fake,
    )
    return fake
