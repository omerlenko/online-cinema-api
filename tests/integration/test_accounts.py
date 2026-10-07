from datetime import datetime, timezone, timedelta
from collections.abc import Callable, Awaitable

from httpx import AsyncClient
from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.accounts.models import ActivationToken, UserGroupEnum, RefreshToken
from src.accounts.models import User
from src.core.config import get_settings
from src.core.security import (
    verify_hashed_password,
    decode_token,
    TokenTypeEnum,
    create_refresh_token,
    _create_jwt_token,
    create_access_token,
)
from tests.helpers import auth_headers

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


async def test_login_user(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
):
    password = "Password12345!"
    active_user = await create_user(
        email="user@example.com", password=password, is_active=True
    )
    payload = {"email": active_user.email, "password": password}
    response = await client.post(f"{ACCOUNTS_URL}/login", json=payload)

    assert response.status_code == 200, "Expected status code 200 OK"

    response_data = response.json()
    assert "access_token" in response_data
    assert "refresh_token" in response_data
    assert "token_type" in response_data
    assert response_data["token_type"] == "bearer"

    assert (
        decode_token(response_data["access_token"], TokenTypeEnum.ACCESS)
        == active_user.id
    )
    assert (
        decode_token(response_data["refresh_token"], TokenTypeEnum.REFRESH)
        == active_user.id
    )


async def test_login_non_existing_user(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
):
    payload = {"email": "user@example.com", "password": "Password12345!"}
    response = await client.post(f"{ACCOUNTS_URL}/login", json=payload)

    assert response.status_code == 401, "Expected status code 401 Unauthorized"


async def test_login_user_with_wrong_password(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
):
    active_user = await create_user(
        email="user@example.com", password="Password12345!", is_active=True
    )
    payload = {"email": active_user.email, "password": "WrongPassword123!"}
    response = await client.post(f"{ACCOUNTS_URL}/login", json=payload)

    assert response.status_code == 401, "Expected status code 401 Unauthorized"


async def test_login_inactive_user(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
):
    password = "Password12345!"
    inactive_user = await create_user(password=password, is_active=False)
    payload = {"email": inactive_user.email, "password": password}
    response = await client.post(f"{ACCOUNTS_URL}/login", json=payload)

    assert response.status_code == 403, "Expected status code 401 Unauthorized"


async def test_login_user_twice(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
):
    password = "Password12345!"
    user = await create_user(password=password, is_active=True)
    payload = {"email": user.email, "password": password}

    response_1 = await client.post(f"{ACCOUNTS_URL}/login", json=payload)
    assert response_1.status_code == 200, "Expected status code 200 OK"
    response_2 = await client.post(f"{ACCOUNTS_URL}/login", json=payload)
    assert response_2.status_code == 200, "Expected status code 200 OK"

    response_data_1 = response_1.json()
    response_data_2 = response_2.json()
    assert response_data_1["refresh_token"] != response_data_2["refresh_token"]


async def test_get_current_user_detail(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
):
    user = await create_user(is_active=True)
    response = await client.get(f"{ACCOUNTS_URL}/me", headers=auth_headers(user))

    assert response.status_code == 200, "Expected status code 200 OK"
    response_data = response.json()
    assert response_data["id"] == user.id
    assert response_data["group_name"] == "user"


async def test_get_current_user_detail_with_no_auth_header(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
):
    response = await client.get(f"{ACCOUNTS_URL}/me")

    assert response.status_code == 401, "Expected status code 401 Unauthorized"


async def test_get_current_user_detail_with_invalid_token(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
):
    auth_header = {"Authorization": "Bearer " + "X" * 32}
    response = await client.get(f"{ACCOUNTS_URL}/me", headers=auth_header)

    assert response.status_code == 401, "Expected status code 401 Unauthorized"


async def test_get_current_user_detail_with_refresh_token(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
):
    user = await create_user(is_active=True)
    refresh_token = create_refresh_token(
        user.id, expires_at=datetime.now(timezone.utc) + timedelta(days=1)
    )
    auth_header = {"Authorization": f"Bearer {refresh_token}"}
    response = await client.get(f"{ACCOUNTS_URL}/me", headers=auth_header)

    assert response.status_code == 401, "Expected status code 401 Unauthorized"


async def test_get_current_user_detail_with_expired_token(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
):
    user = await create_user(is_active=True)
    expired_access_token = _create_jwt_token(
        user.id,
        token_type=TokenTypeEnum.ACCESS,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    auth_header = {"Authorization": f"Bearer {expired_access_token}"}
    response = await client.get(f"{ACCOUNTS_URL}/me", headers=auth_header)

    assert response.status_code == 401, "Expected status code 401 Unauthorized"


async def test_get_current_user_detail_for_deleted_user(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
):
    user = await create_user(is_active=True)
    access_token = create_access_token(user.id)
    auth_header = {"Authorization": f"Bearer {access_token}"}

    await db_session.delete(user)
    await db_session.flush()
    response = await client.get(f"{ACCOUNTS_URL}/me", headers=auth_header)

    assert response.status_code == 401, "Expected status code 401 Unauthorized"


async def test_get_current_user_detail_with_inactive_user(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
):
    user = await create_user(is_active=False)
    response = await client.get(f"{ACCOUNTS_URL}/me", headers=auth_headers(user))

    assert response.status_code == 403, "Expected status code 403 Forbidden"


async def test_refresh_access_token(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_refresh_token_object: Callable[..., Awaitable[RefreshToken]],
):
    user = await create_user(is_active=True)
    refresh_token_object = await create_refresh_token_object(user_id=user.id)
    payload = {"refresh_token": refresh_token_object.token}
    response = await client.post(f"{ACCOUNTS_URL}/refresh", json=payload)

    assert response.status_code == 200, "Expected status code 200 OK"

    response_data = response.json()
    assert "access_token" in response_data, "Access token not in response data"
    assert "token_type" in response_data, "Token type not in response data"
    assert (
        decode_token(response_data["access_token"], TokenTypeEnum.ACCESS) == user.id
    ), "User id not in access token payload"

    auth_header = {"Authorization": f"Bearer {response_data["access_token"]}"}
    me_response = await client.get(f"{ACCOUNTS_URL}/me", headers=auth_header)
    assert me_response.status_code == 200, "Expected status code 200 OK"


async def test_refresh_access_token_with_access_token(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
):
    user = await create_user(is_active=True)
    access_token = create_access_token(user.id)
    payload = {"refresh_token": access_token}
    response = await client.post(f"{ACCOUNTS_URL}/refresh", json=payload)

    assert response.status_code == 401, "Expected status code 401 Unauthorized"


async def test_refresh_access_token_with_expired_refresh_token(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_refresh_token_object: Callable[..., Awaitable[RefreshToken]],
):
    user = await create_user(is_active=True)
    expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    refresh_token_object = await create_refresh_token_object(
        user_id=user.id, expires_at=expires_at
    )
    payload = {"refresh_token": refresh_token_object.token}
    response = await client.post(f"{ACCOUNTS_URL}/refresh", json=payload)

    assert response.status_code == 401, "Expected status code 401 Unauthorized"


async def test_refresh_access_token_with_no_refresh_token_in_db(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    user = await create_user(is_active=True)
    expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    refresh_token = create_refresh_token(user.id, expires_at=expires_at)
    payload = {"refresh_token": refresh_token}
    response = await client.post(f"{ACCOUNTS_URL}/refresh", json=payload)

    assert response.status_code == 401, "Expected status code 401 Unauthorized"


async def test_refresh_access_token_with_inactive_user(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_refresh_token_object: Callable[..., Awaitable[RefreshToken]],
):
    user = await create_user(is_active=False)
    refresh_token_object = await create_refresh_token_object(user_id=user.id)
    payload = {"refresh_token": refresh_token_object.token}
    response = await client.post(f"{ACCOUNTS_URL}/refresh", json=payload)

    assert response.status_code == 403, "Expected status code 403 Forbidden"


async def test_logout_user(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_refresh_token_object: Callable[..., Awaitable[RefreshToken]],
):
    user = await create_user(is_active=True)
    refresh_token_object = await create_refresh_token_object(user_id=user.id)
    payload = {"refresh_token": refresh_token_object.token}
    response = await client.post(f"{ACCOUNTS_URL}/logout", json=payload)

    assert response.status_code == 204, "Expected status code 204 No Content"
    assert (
        await db_session.scalar(
            select(exists().where(RefreshToken.token == refresh_token_object.token))
        )
        is False
    )

    payload = {"refresh_token": refresh_token_object.token}
    refresh_response = await client.post(f"{ACCOUNTS_URL}/refresh", json=payload)
    assert refresh_response.status_code == 401, "Expected status code 401 Unauthorized"


async def test_logout_user_with_multiple_refresh_tokens(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_refresh_token_object: Callable[..., Awaitable[RefreshToken]],
):
    user = await create_user(is_active=True)
    refresh_token_object_1 = await create_refresh_token_object(user_id=user.id)
    refresh_token_object_2 = await create_refresh_token_object(user_id=user.id)
    payload = {"refresh_token": refresh_token_object_1.token}
    response = await client.post(f"{ACCOUNTS_URL}/logout", json=payload)

    assert response.status_code == 204, "Expected status code 204 No Content"

    payload = {"refresh_token": refresh_token_object_2.token}
    refresh_response = await client.post(f"{ACCOUNTS_URL}/refresh", json=payload)
    assert refresh_response.status_code == 200, "Expected status code 200 OK"


async def test_logout_user_twice(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_refresh_token_object: Callable[..., Awaitable[RefreshToken]],
):
    user = await create_user(is_active=True)
    refresh_token_object = await create_refresh_token_object(user_id=user.id)
    payload = {"refresh_token": refresh_token_object.token}
    response = await client.post(f"{ACCOUNTS_URL}/logout", json=payload)

    assert response.status_code == 204, "Expected status code 204 No Content"
    response_2 = await client.post(f"{ACCOUNTS_URL}/logout", json=payload)
    assert response_2.status_code == 204, "Expected status code 204 No Content"
