from datetime import datetime, timezone, timedelta

import jwt
import pytest

from src.core.config import get_settings
from src.core.security import (
    create_access_token,
    decode_token,
    TokenTypeEnum,
    create_refresh_token,
    InvalidTokenError,
)

settings = get_settings()


def test_decode_token_with_valid_token():
    access_token = create_access_token(user_id=1)
    user_id = decode_token(access_token, TokenTypeEnum.ACCESS)

    assert isinstance(user_id, int)
    assert user_id == 1


def test_decode_token_with_wrong_token_type():
    expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    refresh_token = create_refresh_token(user_id=1, expires_at=expires_at)

    with pytest.raises(InvalidTokenError, match="Unexpected token type"):
        decode_token(refresh_token, TokenTypeEnum.ACCESS)


def test_decode_token_with_expired_token():
    expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    refresh_token = create_refresh_token(user_id=1, expires_at=expires_at)

    with pytest.raises(InvalidTokenError):
        decode_token(refresh_token, TokenTypeEnum.REFRESH)


def test_decode_token_with_tampered_token():
    expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    payload = {
        "sub": "1",
        "exp": expires_at,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    access_token = jwt.encode(
        payload=payload, key="absolutely_wrong_secret_key_1234", algorithm="HS256"
    )

    with pytest.raises(InvalidTokenError):
        decode_token(access_token, TokenTypeEnum.ACCESS)


def test_decode_token_with_missing_claims():
    payload = {
        "sub": "1",
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    access_token = jwt.encode(
        payload=payload, key=settings.JWT_SECRET_KEY, algorithm="HS256"
    )

    with pytest.raises(InvalidTokenError):
        decode_token(access_token, TokenTypeEnum.ACCESS)


def test_decode_token_with_non_numeric_sub():
    expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    payload = {
        "sub": "abc",
        "exp": expires_at,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    access_token = jwt.encode(
        payload=payload, key=settings.JWT_SECRET_KEY, algorithm="HS256"
    )

    with pytest.raises(InvalidTokenError):
        decode_token(access_token, TokenTypeEnum.ACCESS)
