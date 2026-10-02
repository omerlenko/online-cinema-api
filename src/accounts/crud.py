from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.models import UserGroup, UserGroupEnum, ActivationToken
from src.accounts.schemas import UserRegistrationRequestSchema
from src.accounts.models import User
from src.core.security import hash_password, generate_token


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    user = await db.scalar(select(User).where(User.email == email))
    return user


async def get_user_by_id(db: AsyncSession, id: int) -> User | None:
    user = await db.scalar(select(User).where(User.id == id))
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
    activation_token = ActivationToken(user_id=user_id, token=token)
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
