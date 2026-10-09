from datetime import datetime, timezone, timedelta

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.accounts.models import (
    UserGroup,
    UserGroupEnum,
    ActivationToken,
    RefreshToken,
    PasswordResetToken,
)
from src.accounts.schemas import UserRegistrationRequestSchema
from src.accounts.models import User
from src.core.config import get_settings
from src.core.security import (
    hash_password,
    generate_token,
    create_refresh_token,
    hash_token,
)

settings = get_settings()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    user = await db.scalar(select(User).where(User.email == email))
    return user


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    user = await db.scalar(
        select(User).options(joinedload(User.group)).where(User.id == user_id)
    )
    return user


async def get_user_group_by_name(
    db: AsyncSession, name: UserGroupEnum
) -> UserGroup | None:
    user_group = await db.scalar(select(UserGroup).where(UserGroup.name == name))
    return user_group


async def create_user(
    db: AsyncSession, data: UserRegistrationRequestSchema, user_group: UserGroup
) -> User:
    hashed_password = hash_password(data.password)
    user = User(
        email=data.email, hashed_password=hashed_password, group_id=user_group.id
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def create_activation_token(db: AsyncSession, user_id: int) -> ActivationToken:
    token = generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.ACTIVATION_TOKEN_LIFETIME_DAYS
    )
    activation_token = ActivationToken(
        user_id=user_id, token=token, expires_at=expires_at
    )
    db.add(activation_token)
    await db.flush()
    await db.refresh(activation_token)
    return activation_token


async def get_activation_token(db: AsyncSession, token: str) -> ActivationToken | None:
    activation_token = await db.scalar(
        select(ActivationToken).where(ActivationToken.token == token)
    )
    return activation_token


async def get_activation_token_by_user_id(
    db: AsyncSession, user_id: int
) -> ActivationToken | None:
    activation_token = await db.scalar(
        select(ActivationToken).where(ActivationToken.user_id == user_id)
    )
    return activation_token


async def delete_activation_token(
    db: AsyncSession, activation_token: ActivationToken
) -> None:
    await db.delete(activation_token)
    await db.flush()


async def create_refresh_token_object(
    db: AsyncSession,
    user_id: int,
) -> RefreshToken:
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_LIFETIME_DAYS
    )
    token = create_refresh_token(user_id, expires_at)
    refresh_token = RefreshToken(user_id=user_id, token=token, expires_at=expires_at)
    db.add(refresh_token)
    await db.flush()
    await db.refresh(refresh_token)
    return refresh_token


async def get_refresh_token_object_by_token(
    db: AsyncSession, token: str
) -> RefreshToken | None:
    refresh_token = await db.scalar(
        select(RefreshToken).where(RefreshToken.token == token)
    )
    return refresh_token


async def delete_refresh_token_object(
    db: AsyncSession, refresh_token_object: RefreshToken
) -> None:
    await db.delete(refresh_token_object)
    await db.flush()


async def delete_refresh_token_objects_by_user_id(
    db: AsyncSession, user_id: int, current_token: str | None = None
) -> None:
    """
    Deletes all refresh tokens by user_id, or all except the current_token if present
    """
    if current_token:
        await db.execute(
            delete(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .where(RefreshToken.token != current_token)
        )
    else:
        await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
    await db.flush()


async def create_password_reset_token(
    db: AsyncSession, user_id: int, plain_token: str
) -> PasswordResetToken:
    hashed_token = hash_token(plain_token)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.PASSWORD_RESET_TOKEN_LIFETIME_MINUTES
    )
    password_reset_token = PasswordResetToken(
        user_id=user_id, token=hashed_token, expires_at=expires_at
    )
    db.add(password_reset_token)
    await db.flush()
    return password_reset_token


async def get_password_reset_token(
    db: AsyncSession, token: str
) -> PasswordResetToken | None:
    password_reset_token = await db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token == token)
    )
    return password_reset_token


async def delete_password_reset_token_by_user_id(
    db: AsyncSession, user_id: int
) -> None:
    await db.execute(
        delete(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
    )
    await db.flush()
