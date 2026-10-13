from collections.abc import Awaitable, Callable, Coroutine
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.crud import delete_expired_tokens
from src.accounts.models import User, ActivationToken, RefreshToken, PasswordResetToken


async def test_delete_expired_tokens(
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_activation_token: Callable[..., Awaitable[ActivationToken]],
    create_refresh_token_object: Callable[..., Awaitable[RefreshToken]],
    create_reset_token: Callable[
        ..., Coroutine[Any, Any, tuple[PasswordResetToken, str]]
    ],
):
    user_1 = await create_user(email="user1@example.com", is_active=True)
    user_2 = await create_user(email="user2@example.com", is_active=True)
    expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

    await create_activation_token(user_id=user_1.id)
    await create_activation_token(user_id=user_2.id, expires_at=expires_at)

    await create_refresh_token_object(user_id=user_1.id)
    await create_refresh_token_object(user_id=user_2.id, expires_at=expires_at)

    await create_reset_token(user_id=user_1.id)
    await create_reset_token(user_id=user_2.id, expires_at=expires_at)

    delete_count = await delete_expired_tokens(db=db_session)
    assert delete_count == 3, "The number of deleted expired tokens is not 3"

    result = await db_session.scalars(select(ActivationToken))
    activation_list = result.all()
    assert len(activation_list) == 1, "Expected exactly 1 surviving activation token"
    assert (
        activation_list[0].user_id == user_1.id
    ), "The wrong activation token survived"

    result = await db_session.scalars(select(RefreshToken))
    refresh_list = result.all()
    assert len(refresh_list) == 1, "Expected exactly 1 surviving refresh token"
    assert refresh_list[0].user_id == user_1.id, "The wrong refresh token survived"

    result = await db_session.scalars(select(PasswordResetToken))
    reset_list = result.all()
    assert len(reset_list) == 1, "Expected exactly 1 surviving password reset token"
    assert reset_list[0].user_id == user_1.id, "The wrong password reset token survived"


async def test_delete_expired_tokens_none_expired(
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_activation_token: Callable[..., Awaitable[ActivationToken]],
    create_refresh_token_object: Callable[..., Awaitable[RefreshToken]],
    create_reset_token: Callable[
        ..., Coroutine[Any, Any, tuple[PasswordResetToken, str]]
    ],
):
    user_1 = await create_user(email="user1@example.com", is_active=True)
    user_2 = await create_user(email="user2@example.com", is_active=True)

    await create_activation_token(user_id=user_1.id)
    await create_activation_token(user_id=user_2.id)

    await create_refresh_token_object(user_id=user_1.id)
    await create_refresh_token_object(user_id=user_2.id)

    await create_reset_token(user_id=user_1.id)
    await create_reset_token(user_id=user_2.id)

    delete_count = await delete_expired_tokens(db=db_session)
    assert delete_count == 0, "The number of deleted expired tokens is not 0"

    count_activation_tokens = await db_session.scalar(
        select(func.count(ActivationToken.id))
    )
    assert (
        count_activation_tokens == 2
    ), "The number of activation tokens in the database is not exactly 2"
    count_refresh_tokens = await db_session.scalar(select(func.count(RefreshToken.id)))
    assert (
        count_refresh_tokens == 2
    ), "The number of refresh tokens in the database is not exactly 2"
    count_reset_tokens = await db_session.scalar(
        select(func.count(PasswordResetToken.id))
    )
    assert (
        count_reset_tokens == 2
    ), "The number of password reset tokens in the database is not exactly 2"
