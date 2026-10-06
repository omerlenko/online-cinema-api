import secrets
from datetime import datetime, timedelta, timezone

import jwt
from enum import Enum
from pwdlib import PasswordHash

from src.core.config import get_settings

password_hash = PasswordHash.recommended()
settings = get_settings()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_hashed_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def generate_token() -> str:
    return secrets.token_urlsafe(32)


class TokenTypeEnum(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


def _create_jwt_token(
    user_id: int,
    token_type: TokenTypeEnum,
    expires_at: datetime,
) -> str:
    payload = {
        "sub": str(user_id),
        "exp": expires_at,
        "iat": datetime.now(timezone.utc),
        "type": token_type.value,
    }
    return jwt.encode(
        payload=payload, key=settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_access_token(user_id: int) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_LIFETIME_MINUTES
    )
    return _create_jwt_token(user_id, TokenTypeEnum.ACCESS, expires_at)


def create_refresh_token(user_id: int, expires_at: datetime) -> str:
    return _create_jwt_token(user_id, TokenTypeEnum.REFRESH, expires_at)


class InvalidTokenError(Exception):
    """Raised when a token is invalid"""


def decode_token(token: str, expected_type: TokenTypeEnum) -> int:
    try:
        token_payload = jwt.decode(
            token,
            key=settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("Invalid token") from exc

    if token_payload["type"] != expected_type.value:
        raise InvalidTokenError("Unexpected token type")
    try:
        user_id = int(token_payload["sub"])
    except ValueError as exc:
        raise InvalidTokenError("User id in the payload is not numeric") from exc

    return user_id
