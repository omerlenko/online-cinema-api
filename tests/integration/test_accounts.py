from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.accounts.models import ActivationToken, UserGroupEnum
from src.accounts.models import User
from src.core.config import get_settings
from src.core.security import verify_hashed_password

settings = get_settings()
ACCOUNTS_URL = f"{settings.API_VERSION_PREFIX}/accounts"


async def test_register_user(
    client: AsyncClient, db_session: AsyncSession, fake_email_sender
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
