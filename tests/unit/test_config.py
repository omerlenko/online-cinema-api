import pytest
from pydantic import ValidationError

from src.core.config import Settings


def test_jwt_secret_key_with_short_key():
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(JWT_SECRET_KEY="X" * 31)
