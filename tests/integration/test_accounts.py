from datetime import datetime, timezone, timedelta
from collections.abc import Callable, Awaitable, Coroutine
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, exists, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.accounts.create_admin import create_admin
from src.accounts.models import (
    ActivationToken,
    UserGroupEnum,
    RefreshToken,
    PasswordResetToken,
    UserGroup,
)
from src.accounts.models import User
from src.accounts.schemas import UserRegistrationRequestSchema
from src.core.config import get_settings
from src.core.security import (
    verify_hashed_password,
    decode_token,
    TokenTypeEnum,
    create_refresh_token,
    _create_jwt_token,
    create_access_token,
    hash_token,
)
from tests.helpers import auth_headers, FakeEmailSender, extract_reset_token_from_email

settings = get_settings()
ACCOUNTS_URL = f"{settings.API_VERSION_PREFIX}/accounts"


async def test_register_user(
    client: AsyncClient, db_session: AsyncSession, fake_email_sender: FakeEmailSender
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
    create_activation_token: Callable[..., Awaitable[ActivationToken]],
):
    inactive_user = await create_user(is_active=False)
    activation_token = await create_activation_token(user_id=inactive_user.id)

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
    create_activation_token: Callable[..., Awaitable[ActivationToken]],
):
    active_user = await create_user(is_active=True)
    activation_token = await create_activation_token(user_id=active_user.id)

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
    create_activation_token: Callable[..., Awaitable[ActivationToken]],
):
    inactive_user = await create_user(is_active=False)
    expired_activation_token = await create_activation_token(
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
    fake_email_sender: FakeEmailSender,
):
    inactive_user = await create_user(is_active=False)
    payload = {"email": inactive_user.email}
    response = await client.post(f"{ACCOUNTS_URL}/resend-activation", json=payload)

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
    create_activation_token: Callable[..., Awaitable[ActivationToken]],
    fake_email_sender: FakeEmailSender,
):
    inactive_user = await create_user(is_active=False)
    expired_activation_token = await create_activation_token(
        user_id=inactive_user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    payload = {"email": inactive_user.email}
    response = await client.post(f"{ACCOUNTS_URL}/resend-activation", json=payload)

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
    create_activation_token: Callable[..., Awaitable[ActivationToken]],
    fake_email_sender: FakeEmailSender,
):
    inactive_user = await create_user(is_active=False)
    valid_activation_token = await create_activation_token(
        user_id=inactive_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    payload = {"email": inactive_user.email}
    response = await client.post(f"{ACCOUNTS_URL}/resend-activation", json=payload)

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
    fake_email_sender: FakeEmailSender,
):
    payload = {
        "email": "unknown_user@example.com",
    }
    response = await client.post(f"{ACCOUNTS_URL}/resend-activation", json=payload)

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
    fake_email_sender: FakeEmailSender,
):
    active_user = await create_user(is_active=True)
    payload = {"email": active_user.email}
    response = await client.post(f"{ACCOUNTS_URL}/resend-activation", json=payload)

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

    assert response.status_code == 403, "Expected status code 403 Forbidden"


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
    auth_header = auth_headers(user)

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


async def test_change_password(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_refresh_token_object: Callable[..., Awaitable[RefreshToken]],
):
    old_password = "OldPassword123!"
    new_password = "NewPassword123!"
    payload = {
        "old_password": old_password,
        "new_password": new_password,
    }
    user = await create_user(password=old_password, is_active=True)
    await create_refresh_token_object(user.id)
    await create_refresh_token_object(user.id)
    await create_refresh_token_object(user.id)

    response = await client.post(
        f"{ACCOUNTS_URL}/change-password", json=payload, headers=auth_headers(user)
    )

    assert response.status_code == 200, "Expected status code 200 OK"
    await db_session.refresh(user)
    assert not verify_hashed_password(old_password, user.hashed_password)
    assert verify_hashed_password(new_password, user.hashed_password)
    assert not await db_session.scalar(
        select(exists().where(RefreshToken.user_id == user.id))
    )


async def test_change_password_keeps_current_session(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_refresh_token_object: Callable[..., Awaitable[RefreshToken]],
):
    old_password = "OldPassword123!"
    new_password = "NewPassword123!"
    user = await create_user(password=old_password, is_active=True)
    refresh_token_1 = await create_refresh_token_object(user.id)
    await create_refresh_token_object(user.id)
    await create_refresh_token_object(user.id)
    payload = {
        "old_password": old_password,
        "new_password": new_password,
        "refresh_token": refresh_token_1.token,
    }

    response = await client.post(
        f"{ACCOUNTS_URL}/change-password", json=payload, headers=auth_headers(user)
    )

    assert response.status_code == 200, "Expected status code 200 OK"

    stmt = select(RefreshToken).where(RefreshToken.user_id == user.id)
    result = await db_session.scalars(stmt)
    refresh_tokens = result.all()
    assert len(refresh_tokens) == 1
    assert refresh_tokens[0].id == refresh_token_1.id


async def test_change_password_wrong_old_password(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    old_password = "OldPassword123!"
    new_password = "NewPassword123!"
    payload = {
        "old_password": "WrongPassword123!",
        "new_password": new_password,
    }
    user = await create_user(password=old_password, is_active=True)

    response = await client.post(
        f"{ACCOUNTS_URL}/change-password", json=payload, headers=auth_headers(user)
    )

    assert response.status_code == 400, "Expected status code 400 Bad Request"


async def test_change_password_new_equals_old_password(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    old_password = "OldPassword123!"
    new_password = "OldPassword123!"
    payload = {
        "old_password": old_password,
        "new_password": new_password,
    }
    user = await create_user(password=old_password, is_active=True)

    response = await client.post(
        f"{ACCOUNTS_URL}/change-password", json=payload, headers=auth_headers(user)
    )

    assert response.status_code == 400, "Expected status code 400 Bad Request"


async def test_change_password_weak_new_password(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    old_password = "OldPassword123!"
    new_password = "password"
    payload = {
        "old_password": old_password,
        "new_password": new_password,
    }
    user = await create_user(password=old_password, is_active=True)

    response = await client.post(
        f"{ACCOUNTS_URL}/change-password", json=payload, headers=auth_headers(user)
    )

    assert response.status_code == 422, "Expected status code 422 Unprocessable Content"


async def test_change_password_no_access_token(
    client: AsyncClient,
):
    old_password = "OldPassword123!"
    new_password = "NewPassword123!"
    payload = {
        "old_password": old_password,
        "new_password": new_password,
    }

    response = await client.post(f"{ACCOUNTS_URL}/change-password", json=payload)

    assert response.status_code == 401, "Expected status code 401 Unauthorized"


async def test_forgot_password(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_email_sender: FakeEmailSender,
    create_user: Callable[..., Awaitable[User]],
):
    email = "user@example.com"
    user = await create_user(email=email, is_active=True)
    payload = {"email": "user@example.com"}

    response = await client.post(f"{ACCOUNTS_URL}/forgot-password", json=payload)

    assert response.status_code == 200, "Expected status code 200 OK"

    assert len(fake_email_sender.sent_emails) == 1, "The amount of sent emails is not 1"
    sent_email = fake_email_sender.sent_emails[0]

    plain_token = extract_reset_token_from_email(sent_email.body)
    stored_token = await db_session.scalar(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )
    assert stored_token is not None, "PasswordResetToken does not exist in the database"
    assert stored_token.token != plain_token, "Stored token value equals plain token"
    assert stored_token.token == hash_token(
        plain_token
    ), "Stored token value is not hashed"


async def test_forgot_password_twice(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_email_sender: FakeEmailSender,
    create_user: Callable[..., Awaitable[User]],
):
    email = "user@example.com"
    user = await create_user(email=email, is_active=True)
    payload = {"email": "user@example.com"}

    response_1 = await client.post(f"{ACCOUNTS_URL}/forgot-password", json=payload)
    assert response_1.status_code == 200, "Expected status code 200 OK"
    sent_email_1 = fake_email_sender.sent_emails[0]
    plain_token_1 = extract_reset_token_from_email(sent_email_1.body)

    response_2 = await client.post(f"{ACCOUNTS_URL}/forgot-password", json=payload)
    assert response_2.status_code == 200, "Expected status code 200 OK"
    sent_email_2 = fake_email_sender.sent_emails[1]
    plain_token_2 = extract_reset_token_from_email(sent_email_2.body)

    stmt = select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    result = await db_session.scalars(stmt)
    reset_tokens = result.all()

    assert len(reset_tokens) == 1
    assert reset_tokens[0].token == hash_token(plain_token_2)

    payload = {"new_password": "NewPassword123!", "password_reset_token": plain_token_1}
    response_reset = await client.post(f"{ACCOUNTS_URL}/reset-password", json=payload)
    assert response_reset.status_code == 400, "Expected status code 400 Bad Request"


async def test_forgot_password_with_unknown_email(
    client: AsyncClient,
    fake_email_sender: FakeEmailSender,
):
    payload = {"email": "user@example.com"}
    response = await client.post(f"{ACCOUNTS_URL}/forgot-password", json=payload)

    assert response.status_code == 200, "Expected status code 200 OK"
    assert response.json()["message"] == (
        "If the email belongs to an active account, "
        "password reset instructions have been sent"
    )
    assert len(fake_email_sender.sent_emails) == 0, "The amount of sent emails is not 0"


async def test_forgot_password_with_inactive_user(
    client: AsyncClient,
    fake_email_sender: FakeEmailSender,
    create_user: Callable[..., Awaitable[User]],
):
    email = "user@example.com"
    await create_user(email=email, is_active=False)
    payload = {"email": "user@example.com"}
    response = await client.post(f"{ACCOUNTS_URL}/forgot-password", json=payload)

    assert response.status_code == 200, "Expected status code 200 OK"
    assert response.json()["message"] == (
        "If the email belongs to an active account, "
        "password reset instructions have been sent"
    )
    assert len(fake_email_sender.sent_emails) == 0, "The amount of sent emails is not 0"


async def test_reset_password(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_refresh_token_object: Callable[..., Awaitable[RefreshToken]],
    create_reset_token: Callable[
        ..., Coroutine[Any, Any, tuple[PasswordResetToken, str]]
    ],
):
    old_password = "OldPassword123!"
    new_password = "NewPassword123!"
    user = await create_user(password=old_password, is_active=True)
    password_reset_token, plain_token = await create_reset_token(user_id=user.id)
    await create_refresh_token_object(user.id)
    await create_refresh_token_object(user.id)
    payload = {
        "new_password": new_password,
        "password_reset_token": plain_token,
    }

    response = await client.post(f"{ACCOUNTS_URL}/reset-password", json=payload)

    assert response.status_code == 200, "Expected status code 200 OK"
    await db_session.refresh(user)
    assert not verify_hashed_password(old_password, user.hashed_password)
    assert verify_hashed_password(new_password, user.hashed_password)
    assert not await db_session.scalar(
        select(exists().where(PasswordResetToken.user_id == user.id))
    )

    stmt = select(RefreshToken).where(RefreshToken.user_id == user.id)
    result = await db_session.scalars(stmt)
    refresh_tokens = result.all()
    assert len(refresh_tokens) == 0


async def test_reset_password_twice(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_reset_token: Callable[
        ..., Coroutine[Any, Any, tuple[PasswordResetToken, str]]
    ],
):
    new_password = "NewPassword123!"
    user = await create_user(is_active=True)
    password_reset_token, plain_token = await create_reset_token(user_id=user.id)
    payload = {
        "new_password": new_password,
        "password_reset_token": plain_token,
    }

    response = await client.post(f"{ACCOUNTS_URL}/reset-password", json=payload)
    assert response.status_code == 200, "Expected status code 200 OK"

    response = await client.post(f"{ACCOUNTS_URL}/reset-password", json=payload)
    assert response.status_code == 400, "Expected status code 400 Bad Request"


async def test_reset_password_with_expired_token(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_reset_token: Callable[
        ..., Coroutine[Any, Any, tuple[PasswordResetToken, str]]
    ],
):
    new_password = "NewPassword123!"
    user = await create_user(is_active=True)
    expires_at = datetime.now(timezone.utc) - timedelta(minutes=60)
    password_reset_token, plain_token = await create_reset_token(
        user_id=user.id, expires_at=expires_at
    )
    payload = {
        "new_password": new_password,
        "password_reset_token": plain_token,
    }

    response = await client.post(f"{ACCOUNTS_URL}/reset-password", json=payload)
    assert response.status_code == 400, "Expected status code 400 Bad Request"


async def test_reset_password_with_unknown_token(
    client: AsyncClient,
):
    new_password = "NewPassword123!"
    plain_token = "Unknown_Token"
    payload = {
        "new_password": new_password,
        "password_reset_token": plain_token,
    }

    response = await client.post(f"{ACCOUNTS_URL}/reset-password", json=payload)
    assert response.status_code == 400, "Expected status code 400 Bad Request"


async def test_reset_password_with_weak_password(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_reset_token: Callable[
        ..., Coroutine[Any, Any, tuple[PasswordResetToken, str]]
    ],
):
    weak_password = "password"
    user = await create_user(is_active=True)
    password_reset_token, plain_token = await create_reset_token(user_id=user.id)
    payload_1 = {
        "new_password": weak_password,
        "password_reset_token": plain_token,
    }

    response = await client.post(f"{ACCOUNTS_URL}/reset-password", json=payload_1)
    assert response.status_code == 422, "Expected status code 422 Unprocessable Content"

    strong_password = "NewPassword123!"
    payload_2 = {
        "new_password": strong_password,
        "password_reset_token": plain_token,
    }
    response = await client.post(f"{ACCOUNTS_URL}/reset-password", json=payload_2)
    assert response.status_code == 200, "Expected status code 200 OK"


async def test_admin_activate_user(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
):
    admin_user = await create_user(
        email="admin@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )
    inactive_user = await create_user(
        email="user@example.com", is_active=False, user_group=UserGroupEnum.USER
    )

    response = await client.post(
        f"{ACCOUNTS_URL}/users/{inactive_user.id}/activate",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200, "Expected status code 200 OK"

    await db_session.refresh(inactive_user)
    assert inactive_user.is_active, "Inactive user was not activated"


async def test_admin_activate_user_with_already_active_user(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
):
    admin_user = await create_user(
        email="admin@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )
    active_user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    response = await client.post(
        f"{ACCOUNTS_URL}/users/{active_user.id}/activate",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200, "Expected status code 200 OK"


async def test_admin_activate_user_with_unknown_user(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    admin_user = await create_user(
        email="admin@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )

    response = await client.post(
        f"{ACCOUNTS_URL}/users/12345/activate",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 404, "Expected status code 404 Not Found"


async def test_admin_activate_user_with_no_access_token(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    inactive_user = await create_user(
        email="user@example.com", is_active=False, user_group=UserGroupEnum.USER
    )

    response = await client.post(f"{ACCOUNTS_URL}/users/{inactive_user.id}/activate")
    assert response.status_code == 401, "Expected status code 401 Unauthorized"


@pytest.mark.parametrize(
    "user_group",
    [
        UserGroupEnum.MODERATOR,
        UserGroupEnum.USER,
    ],
)
async def test_admin_activate_user_with_no_permission(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    user_group: UserGroupEnum,
):
    user = await create_user(
        email="regular_user@example.com", is_active=True, user_group=user_group
    )
    inactive_user = await create_user(
        email="user@example.com", is_active=False, user_group=UserGroupEnum.USER
    )

    response = await client.post(
        f"{ACCOUNTS_URL}/users/{inactive_user.id}/activate",
        headers=auth_headers(user),
    )
    assert response.status_code == 403, "Expected status code 403 Forbidden"


async def test_admin_change_group(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
):
    admin_user = await create_user(
        email="admin@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )
    regular_user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    payload = {"group_name": "moderator"}

    response = await client.post(
        f"{ACCOUNTS_URL}/users/{regular_user.id}/change-group",
        json=payload,
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200, "Expected status code 200 OK"

    user = await db_session.scalar(
        select(User).options(joinedload(User.group)).where(User.id == regular_user.id)
    )
    assert user is not None, "User not found"
    assert user.group.name == "moderator", "User group was not changed"


async def test_admin_change_own_group(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
):
    admin_user = await create_user(
        email="admin@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )
    payload = {"group_name": "moderator"}

    response = await client.post(
        f"{ACCOUNTS_URL}/users/{admin_user.id}/change-group",
        json=payload,
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 403, "Expected status code 403 Forbidden"

    user = await db_session.scalar(
        select(User).options(joinedload(User.group)).where(User.id == admin_user.id)
    )
    assert user is not None, "User was not found"
    assert user.group.name == "admin", "User group was changed"


async def test_admin_demote_another_admin(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
):
    admin_user = await create_user(
        email="admin@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )
    admin_user_2 = await create_user(
        email="admin2@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )

    payload = {"group_name": "user"}

    response = await client.post(
        f"{ACCOUNTS_URL}/users/{admin_user_2.id}/change-group",
        json=payload,
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200, "Expected status code 200 OK"

    user = await db_session.scalar(
        select(User).options(joinedload(User.group)).where(User.id == admin_user_2.id)
    )
    assert user is not None, "User not found"
    assert user.group.name == "user", "User group was not changed"


async def test_admin_change_group_to_same_group(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    admin_user = await create_user(
        email="admin@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )
    moderator_user = await create_user(
        email="moderator@example.com",
        is_active=True,
        user_group=UserGroupEnum.MODERATOR,
    )

    payload = {"group_name": "moderator"}

    response = await client.post(
        f"{ACCOUNTS_URL}/users/{moderator_user.id}/change-group",
        json=payload,
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200, "Expected status code 200 OK"


async def test_admin_change_group_with_unknown_user(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    admin_user = await create_user(
        email="admin@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )
    payload = {"group_name": "admin"}

    response = await client.post(
        f"{ACCOUNTS_URL}/users/12345/change-group",
        json=payload,
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 404, "Expected status code 404 Not Found"


async def test_admin_change_group_with_no_access_token(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    regular_user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    payload = {"group_name": "admin"}

    response = await client.post(
        f"{ACCOUNTS_URL}/users/{regular_user.id}/change-group",
        json=payload,
    )
    assert response.status_code == 401, "Expected status code 401 Unauthorized"


@pytest.mark.parametrize(
    "user_group",
    [
        UserGroupEnum.MODERATOR,
        UserGroupEnum.USER,
    ],
)
async def test_admin_change_group_with_no_permission(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    user_group: UserGroupEnum,
):
    caller = await create_user(
        email="user1@example.com", is_active=True, user_group=user_group
    )
    target = await create_user(
        email="user2@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    payload = {"group_name": "moderator"}

    response = await client.post(
        f"{ACCOUNTS_URL}/users/{target.id}/change-group",
        json=payload,
        headers=auth_headers(caller),
    )
    assert response.status_code == 403, "Expected status code 403 Forbidden"


async def test_create_admin_command(db_session: AsyncSession):
    password = "Password12345!"
    data = UserRegistrationRequestSchema(email="admin@example.com", password=password)
    created_user = await create_admin(db=db_session, data=data)

    admin_user = await db_session.scalar(
        select(User).options(joinedload(User.group)).where(User.id == created_user.id)
    )
    assert admin_user is not None, "The user is not found"
    assert verify_hashed_password(
        password, admin_user.hashed_password
    ), "The password is invalid"
    assert admin_user.is_active, "The user is not active"
    assert (
        admin_user.group.name == UserGroupEnum.ADMIN
    ), "The user is not in the 'admin' group"


async def test_create_admin_command_with_taken_email(
    db_session: AsyncSession, create_user: Callable[..., Awaitable[User]]
):
    email = "admin@example.com"
    password = "Password12345!"
    await create_user(email=email, password=password)

    data = UserRegistrationRequestSchema(email=email, password=password)

    with pytest.raises(ValueError, match="A user with this email already exists"):
        await create_admin(db=db_session, data=data)


async def test_create_admin_command_with_no_admin_user_group(db_session: AsyncSession):
    password = "Password12345!"
    data = UserRegistrationRequestSchema(email="admin@example.com", password=password)

    await db_session.execute(delete(UserGroup))
    with pytest.raises(
        ValueError, match="Admin group not found. Have the migrations been applied"
    ):
        await create_admin(db=db_session, data=data)


async def test_list_users(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
):
    admin_user = await create_user(
        email="admin@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )
    user_1 = await create_user(
        email="user_1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    user_2 = await create_user(
        email="user_2@example.com", is_active=False, user_group=UserGroupEnum.USER
    )

    response = await client.get(
        f"{ACCOUNTS_URL}/users",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200, "Expected status code 200 OK"
    response_ids = [item["id"] for item in response.json()]
    assert response_ids == [
        admin_user.id,
        user_1.id,
        user_2.id,
    ], "Expected ids are not in the response."
    assert response.json()[1] == {
        "id": user_1.id,
        "email": "user_1@example.com",
        "group_name": "user",
        "is_active": True,
    }, "Response does not have the expected structure."


async def test_list_users_filter_by_email(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
):
    admin_user = await create_user(
        email="admin@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )
    await create_user(
        email="user_1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    user_2 = await create_user(
        email="user_2@example.com", is_active=False, user_group=UserGroupEnum.USER
    )

    response = await client.get(
        f"{ACCOUNTS_URL}/users",
        params={"email": "user_2@example.com"},
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200, "Expected status code 200 OK"
    response_ids = [item["id"] for item in response.json()]
    assert response_ids == [user_2.id], "Expected ids are not in the response."


async def test_list_users_with_limit_and_offset(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
):
    admin_user = await create_user(
        email="admin@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )
    user_1 = await create_user(
        email="user_1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    user_2 = await create_user(
        email="user_2@example.com", is_active=False, user_group=UserGroupEnum.USER
    )

    response_limit = await client.get(
        f"{ACCOUNTS_URL}/users",
        params={"limit": 2, "offset": 0},
        headers=auth_headers(admin_user),
    )
    assert response_limit.status_code == 200, "Expected status code 200 OK"
    response_ids = [item["id"] for item in response_limit.json()]
    assert response_ids == [
        admin_user.id,
        user_1.id,
    ], "Expected ids are not in the response."

    response_offset = await client.get(
        f"{ACCOUNTS_URL}/users",
        params={"limit": 2, "offset": 2},
        headers=auth_headers(admin_user),
    )
    assert response_offset.status_code == 200, "Expected status code 200 OK"
    response_ids = [item["id"] for item in response_offset.json()]
    assert response_ids == [user_2.id], "Expected id is not in the response."


async def test_list_users_with_no_permission(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
):
    regular_user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    response = await client.get(
        f"{ACCOUNTS_URL}/users",
        headers=auth_headers(regular_user),
    )
    assert response.status_code == 403, "Expected status code 403 Forbidden"
