from unittest.mock import MagicMock, AsyncMock

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_db
from src.main import app


async def test_health(client: AsyncClient):
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "ok", "database": "ok"}


async def test_health_returns_503_when_db_unavailable(client: AsyncClient, monkeypatch):
    mock_db = MagicMock(spec=AsyncSession)
    mock_db.execute = AsyncMock(side_effect=OSError())

    async def override_get_db():
        yield mock_db

    monkeypatch.setitem(app.dependency_overrides, get_db, override_get_db)
    response = await client.get("/health")

    assert response.status_code == 503
    data = response.json()
    assert data == {"detail": "Database unavailable"}
