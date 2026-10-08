from collections.abc import Callable, Awaitable

import pytest
from httpx import AsyncClient

from src.accounts.models import User

pytestmark = pytest.mark.parametrize(
    "url",
    [
        "/openapi.json",
        "/docs",
        "/redoc",
    ],
)


async def test_docs_auth_enabled_with_no_credentials(
    client: AsyncClient,
    url: str,
    toggle_docs_auth: Callable[[bool], None],
):
    toggle_docs_auth(True)

    response = await client.get(url=url)
    assert response.status_code == 401, "Expected status code 401 Unauthorized"
    assert response.headers["WWW-Authenticate"] == "Basic"


async def test_docs_auth_enabled_with_wrong_password(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    url: str,
    toggle_docs_auth: Callable[[bool], None],
):
    toggle_docs_auth(True)

    email = "user@example.com"
    password = "Password12345!"
    await create_user(email=email, password=password, is_active=True)

    response = await client.get(url=url, auth=(email, "WrongPass123!"))
    assert response.status_code == 401, "Expected status code 401 Unauthorized"


async def test_docs_auth_enabled_with_unknown_email(
    client: AsyncClient,
    url: str,
    toggle_docs_auth: Callable[[bool], None],
):
    toggle_docs_auth(True)

    email = "unknown_user@example.com"
    password = "Password12345!"

    response = await client.get(url=url, auth=(email, password))
    assert response.status_code == 401, "Expected status code 401 Unauthorized"


async def test_docs_auth_enabled_with_inactive_user(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    url: str,
    toggle_docs_auth: Callable[[bool], None],
):
    toggle_docs_auth(True)

    email = "user@example.com"
    password = "Password12345!"
    await create_user(email=email, password=password, is_active=False)

    response = await client.get(url=url, auth=(email, password))
    assert response.status_code == 403, "Expected status code 403 Forbidden"


async def test_docs_auth_enabled_with_valid_credentials(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    url: str,
    toggle_docs_auth: Callable[[bool], None],
):
    toggle_docs_auth(True)

    email = "user@example.com"
    password = "Password12345!"
    await create_user(email=email, password=password, is_active=True)

    response = await client.get(url=url, auth=(email, password))
    assert response.status_code == 200, "Expected status code 200 OK"


async def test_docs_auth_enabled_with_valid_credentials_case_insensitive(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    url: str,
    toggle_docs_auth: Callable[[bool], None],
):
    toggle_docs_auth(True)

    email = "user@example.com"
    email_wrong_case = "USER@EXAMPLE.COM"
    password = "Password12345!"
    await create_user(email=email, password=password, is_active=True)

    response = await client.get(url=url, auth=(email_wrong_case, password))
    assert response.status_code == 200, "Expected status code 200 OK"


async def test_docs_auth_disabled(
    client: AsyncClient,
    url: str,
    toggle_docs_auth: Callable[[bool], None],
):
    toggle_docs_auth(False)

    response = await client.get(url=url)
    assert response.status_code == 200, "Expected status code 200 OK"
