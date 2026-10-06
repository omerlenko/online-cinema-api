from src.accounts.models import User
from src.core.security import create_access_token


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}
