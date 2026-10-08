from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import (
    HTTPBearer,
    HTTPAuthorizationCredentials,
    HTTPBasic,
    HTTPBasicCredentials,
)

from src.accounts.crud import get_user_by_id, get_user_by_email
from src.accounts.models import User
from src.core.config import get_settings
from src.core.security import (
    decode_token,
    TokenTypeEnum,
    InvalidTokenError,
    verify_hashed_password,
)
from src.database.session import DbDep

settings = get_settings()

bearer_scheme = HTTPBearer()
BearerSchemeDep = Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)]
basic_scheme = HTTPBasic(auto_error=False)
BasicSchemeDep = Annotated[HTTPBasicCredentials | None, Depends(basic_scheme)]


async def get_current_user(db: DbDep, credentials: BearerSchemeDep) -> User:
    token = credentials.credentials

    try:
        user_id = decode_token(token, expected_type=TokenTypeEnum.ACCESS)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await get_user_by_id(db=db, user_id=user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Inactive account",
        )

    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def validate_docs_credentials(db: DbDep, credentials: BasicSchemeDep) -> None:
    if not settings.DOCS_REQUIRE_AUTH:
        return

    auth_header = {"WWW-Authenticate": "Basic"}

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers=auth_header,
        )
    email = credentials.username.strip().lower()
    password = credentials.password

    user = await get_user_by_email(db=db, email=email)
    if user is None or not verify_hashed_password(password, user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Password or email is incorrect",
            headers=auth_header,
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive account")
