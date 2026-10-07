from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.accounts.crud import get_user_by_id
from src.accounts.models import User
from src.core.security import decode_token, TokenTypeEnum, InvalidTokenError
from src.database.session import DbDep

bearer_scheme = HTTPBearer()
BearerSchemeDep = Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)]


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
