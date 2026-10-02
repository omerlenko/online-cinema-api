from datetime import datetime, timezone, timedelta
from collections.abc import Callable, Awaitable

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.accounts.models import ActivationToken, UserGroupEnum
from src.accounts.models import User
from src.core.config import get_settings
from src.core.security import verify_hashed_password

settings = get_settings()
ACCOUNTS_URL = f"{settings.API_VERSION_PREFIX}/accounts"


async def test_register_user(
    client: AsyncClient, db_session: AsyncSession, fake_email_sender
):
    payload = {
        "email": "test_user@example.com",
        "password": "Password12345!",
    }
    response = await client.post(
        f"{ACCOUNTS_URL}/register",
        json=payload,
    )

    assert response.status_code == 201, "Expected status code 201 Created"
    response_data = response.json()
    assert "id" in response_data, "Response does not contain id"
    assert response_data["email"] == payload["email"], "Returned email does not match"

    stmt_user = (
        select(User)
        .options(joinedload(User.group))
        .where(User.email == payload["email"])
    )
    created_user = await db_session.scalar(stmt_user)
    assert created_user is not None, "User was not created in the database"
    assert created_user.email == payload["email"], "Created user's email does not match"

    assert created_user.is_active is False, "Created user is active"
    assert (
        created_user.group.name == UserGroupEnum.USER
    ), "Created user's group is not USER"
    assert (
        verify_hashed_password(payload["password"], created_user.hashed_password)
        is True
    ), "Created user's password is not hashed"

    stmt_token = select(ActivationToken).where(
        ActivationToken.user_id == created_user.id
    )
    activation_token = await db_session.scalar(stmt_token)
    assert (
        activation_token is not None
    ), "ActivationToken was not created in the database"

    assert len(fake_email_sender.sent_emails) == 1, "The amount of sent emails is not 1"
    sent_email = fake_email_sender.sent_emails[0]
    assert (
        created_user.email == sent_email.to
    ), "Activation email recipient address is not created user's email"
    assert (
        activation_token.token in sent_email.body
    ), "Activation email does not contain activation token"


async def test_register_user_with_existing_email(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
):
    payload = {
        "email": "existing_user@example.com",
        "password": "Password12345!",
    }
    await create_user(email=payload["email"], password=payload["password"])
    response = await client.post(f"{ACCOUNTS_URL}/register", json=payload)

    assert response.status_code == 409, "Expected status code 409 Conflict"


async def test_register_user_with_weak_password(client: AsyncClient):
    payload = {
        "email": "test_user@example.com",
        "password": "password",
    }
    response = await client.post(f"{ACCOUNTS_URL}/register", json=payload)

    assert response.status_code == 422, "Expected status code 422 Unprocessable Entity"


async def test_activate_user(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_token: Callable[..., Awaitable[ActivationToken]],
):
    inactive_user = await create_user(is_active=False)
    activation_token = await create_token(user_id=inactive_user.id)

    response = await client.get(
        f"{ACCOUNTS_URL}/activate", params={"token": activation_token.token}
    )
    await db_session.refresh(inactive_user)

    assert response.status_code == 200, "Expected status code 200 OK"
    response_data = response.json()
    assert (
        response_data["message"] == "User activated successfully"
    ), "Success message not in response data"
    assert inactive_user.is_active is True, "User has not been activated"


async def test_activate_already_active_user(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_token: Callable[..., Awaitable[ActivationToken]],
):
    active_user = await create_user(is_active=True)
    activation_token = await create_token(user_id=active_user.id)

    response = await client.get(
        f"{ACCOUNTS_URL}/activate", params={"token": activation_token.token}
    )

    assert response.status_code == 200, "Expected status code 200 OK"
    response_data = response.json()
    assert (
        response_data["message"] == "User already active"
    ), "Proper response message not in response data"


async def test_activate_user_with_expired_token(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_token: Callable[..., Awaitable[ActivationToken]],
):
    inactive_user = await create_user(is_active=False)
    expired_activation_token = await create_token(
        user_id=inactive_user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )

    response = await client.get(
        f"{ACCOUNTS_URL}/activate", params={"token": expired_activation_token.token}
    )

    assert response.status_code == 400, "Expected status code 400 Bad Request"


async def test_activate_user_with_invalid_token(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    response = await client.get(
        f"{ACCOUNTS_URL}/activate", params={"token": "INVLDTKN"}
    )
    assert response.status_code == 400, "Expected status code 400 Bad Request"


async def test_resend_activation_token_when_no_token_exists(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    fake_email_sender,
):
    inactive_user = await create_user(is_active=False)
    payload = {"email": inactive_user.email}
    response = await client.post(f"{ACCOUNTS_URL}/resend_activation", json=payload)

    assert response.status_code == 200, "Expected status code 200 OK"

    stmt_token = select(ActivationToken).where(
        ActivationToken.user_id == inactive_user.id
    )
    activation_token = await db_session.scalar(stmt_token)
    assert (
        activation_token is not None
    ), "ActivationToken was not created in the database"

    assert len(fake_email_sender.sent_emails) == 1, "The amount of sent emails is not 1"
    sent_email = fake_email_sender.sent_emails[0]
    assert (
        activation_token.token in sent_email.body
    ), "Activation email does not contain activation token"
    assert (
        sent_email.to == inactive_user.email
    ), "Activation email recipient address is not inactive user's email"


async def test_resend_activation_token_when_token_expired(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_token: Callable[..., Awaitable[ActivationToken]],
    fake_email_sender,
):
    inactive_user = await create_user(is_active=False)
    expired_activation_token = await create_token(
        user_id=inactive_user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    payload = {"email": inactive_user.email}
    response = await client.post(f"{ACCOUNTS_URL}/resend_activation", json=payload)

    assert response.status_code == 200, "Expected status code 200 OK"

    stmt_token = select(ActivationToken).where(
        ActivationToken.user_id == inactive_user.id
    )
    new_activation_token = await db_session.scalar(stmt_token)
    assert (
        new_activation_token is not None
    ), "ActivationToken was not created in the database"
    assert (
        new_activation_token.token != expired_activation_token.token
    ), "New activation token is not different from the expired one"
    assert new_activation_token.expires_at > datetime.now(
        timezone.utc
    ), "New activation token expiry date is not in the future"

    assert len(fake_email_sender.sent_emails) == 1, "The amount of sent emails is not 1"
    sent_email = fake_email_sender.sent_emails[0]
    assert (
        new_activation_token.token in sent_email.body
    ), "Activation email recipient address is not inactive user's email"
    assert (
        sent_email.to == inactive_user.email
    ), "Activation email does not contain activation token"


async def test_resend_activation_token_when_a_valid_token_exists(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_token: Callable[..., Awaitable[ActivationToken]],
    fake_email_sender,
):
    inactive_user = await create_user(is_active=False)
    valid_activation_token = await create_token(
        user_id=inactive_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    payload = {"email": inactive_user.email}
    response = await client.post(f"{ACCOUNTS_URL}/resend_activation", json=payload)

    assert response.status_code == 200, "Expected status code 200 OK"

    stmt_token = select(ActivationToken).where(
        ActivationToken.user_id == inactive_user.id
    )
    activation_token = await db_session.scalar(stmt_token)
    assert (
        activation_token is not None
    ), "ActivationToken does not exist in the database"
    assert (
        activation_token.token == valid_activation_token.token
    ), "Activation token is different from the existing valid one"

    assert len(fake_email_sender.sent_emails) == 1, "The amount of sent emails is not 1"
    sent_email = fake_email_sender.sent_emails[0]
    assert (
        activation_token.token in sent_email.body
    ), "Activation email does not contain activation token"
    assert (
        sent_email.to == inactive_user.email
    ), "Activation email recipient address is not inactive user's email"


async def test_resend_activation_with_unknown_email(
    client: AsyncClient,
    fake_email_sender,
):
    payload = {
        "email": "unknown_user@example.com",
    }
    response = await client.post(f"{ACCOUNTS_URL}/resend_activation", json=payload)

    assert response.status_code == 200, "Expected status code 200 OK"
    response_data = response.json()
    assert (
        response_data["message"] == "If the email belongs to an inactive account, "
        "a new activation link has been sent"
    ), "Proper response message not in response data"

    assert len(fake_email_sender.sent_emails) == 0, "Sent emails list is not empty"


async def test_resend_activation_to_already_active_user(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    fake_email_sender,
):
    active_user = await create_user(is_active=True)
    payload = {"email": active_user.email}
    response = await client.post(f"{ACCOUNTS_URL}/resend_activation", json=payload)

    assert response.status_code == 200, "Expected status code 200 OK"
    response_data = response.json()
    assert (
        response_data["message"] == "If the email belongs to an inactive account, "
        "a new activation link has been sent"
    ), "Proper response message not in response data"

    assert len(fake_email_sender.sent_emails) == 0, "Sent emails list is not empty"
