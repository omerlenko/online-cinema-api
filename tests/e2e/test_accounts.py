from collections.abc import Awaitable, Callable
from urllib.parse import urlparse, parse_qs

from httpx import AsyncClient

from src.accounts.models import User
from src.core.config import get_settings
from tests.helpers import FakeEmailSender, extract_reset_token_from_email

settings = get_settings()
ACCOUNTS_URL = f"{settings.API_VERSION_PREFIX}/accounts"


async def test_register_activate_login_me_refresh_logout(
    client: AsyncClient, fake_email_sender: FakeEmailSender
):
    # register
    payload_register = {
        "email": "user@example.com",
        "password": "Password12345!",
    }
    response_register = await client.post(
        f"{ACCOUNTS_URL}/register", json=payload_register
    )
    assert response_register.status_code == 201, "Expected status code 201 Created"

    # login before activation
    response_login = await client.post(f"{ACCOUNTS_URL}/login", json=payload_register)
    assert response_login.status_code == 403, "Expected status code 403 Forbidden"

    # activation
    assert len(fake_email_sender.sent_emails) == 1
    activation_email = fake_email_sender.sent_emails[0]
    parsed_activation_url = urlparse(activation_email.body)
    params = parse_qs(parsed_activation_url.query)
    activation_token = params.get("token", [None])[0]
    assert activation_token is not None
    response_activate = await client.get(
        f"{ACCOUNTS_URL}/activate", params={"token": activation_token}
    )
    assert response_activate.status_code == 200, "Expected status code 200 OK"

    # login
    response_login = await client.post(f"{ACCOUNTS_URL}/login", json=payload_register)
    assert response_login.status_code == 200, "Expected status code 200 OK"

    # /me
    access_token = response_login.json()["access_token"]
    refresh_token = response_login.json()["refresh_token"]
    auth_header = {"Authorization": f"Bearer {access_token}"}
    response_me = await client.get(f"{ACCOUNTS_URL}/me", headers=auth_header)
    assert response_me.status_code == 200, "Expected status code 200 OK"
    assert response_me.json()["email"] == payload_register["email"]

    # refresh
    payload_refresh = {"refresh_token": refresh_token}
    response_refresh = await client.post(
        f"{ACCOUNTS_URL}/refresh", json=payload_refresh
    )
    assert response_refresh.status_code == 200, "Expected status code 200 OK"

    # repeat /me with a new access token
    auth_header = {"Authorization": f"Bearer {response_refresh.json()["access_token"]}"}
    response_me = await client.get(f"{ACCOUNTS_URL}/me", headers=auth_header)
    assert response_me.status_code == 200, "Expected status code 200 OK"

    # logout
    payload_logout = {"refresh_token": refresh_token}
    response_logout = await client.post(f"{ACCOUNTS_URL}/logout", json=payload_logout)
    assert response_logout.status_code == 204, "Expected status code 204 No Content"

    # repeat refresh
    response_refresh = await client.post(
        f"{ACCOUNTS_URL}/refresh", json=payload_refresh
    )
    assert response_refresh.status_code == 401, "Expected status code 401 Unauthorized"


async def test_login_change_forgot_reset_password(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    fake_email_sender: FakeEmailSender,
):
    email = "user@example.com"
    original_password = "OriginalPassword12345!"
    await create_user(email=email, password=original_password, is_active=True)

    # login
    payload_login = {"email": email, "password": original_password}
    response_login = await client.post(f"{ACCOUNTS_URL}/login", json=payload_login)
    assert response_login.status_code == 200, "Expected status code 200 OK"

    # change password
    access_token = response_login.json()["access_token"]
    refresh_token = response_login.json()["refresh_token"]
    auth_header = {"Authorization": f"Bearer {access_token}"}
    changed_password = "ChangedPassword12345!"
    payload_change_pass = {
        "old_password": original_password,
        "new_password": changed_password,
        "refresh_token": refresh_token,
    }
    response_change_pass = await client.post(
        f"{ACCOUNTS_URL}/change-password", json=payload_change_pass, headers=auth_header
    )
    assert response_change_pass.status_code == 200, "Expected status code 200 OK"
    assert response_change_pass.json()["message"] == "New password set successfully"

    # login with changed password
    payload_login = {"email": email, "password": changed_password}
    response_login = await client.post(f"{ACCOUNTS_URL}/login", json=payload_login)
    assert response_login.status_code == 200, "Expected status code 200 OK"

    # forgot password
    payload_forgot_pass = {"email": email}
    response_forgot_pass = await client.post(
        f"{ACCOUNTS_URL}/forgot-password",
        json=payload_forgot_pass,
    )
    assert response_forgot_pass.status_code == 200, "Expected status code 200 OK"
    assert len(fake_email_sender.sent_emails) == 1, "The amount of sent emails is not 1"
    sent_email = fake_email_sender.sent_emails[0]
    plain_reset_token = extract_reset_token_from_email(sent_email.body)

    # reset password
    reset_password = "ResetPassword12345!"
    payload_reset_pass = {
        "new_password": reset_password,
        "password_reset_token": plain_reset_token,
    }
    response_reset_pass = await client.post(
        f"{ACCOUNTS_URL}/reset-password",
        json=payload_reset_pass,
    )
    assert response_reset_pass.status_code == 200, "Expected status code 200 OK"

    # login with reset password
    payload_login = {"email": email, "password": reset_password}
    response_login = await client.post(f"{ACCOUNTS_URL}/login", json=payload_login)
    assert response_login.status_code == 200, "Expected status code 200 OK"

    # login with changed password
    payload_login = {"email": email, "password": changed_password}
    response_login = await client.post(f"{ACCOUNTS_URL}/login", json=payload_login)
    assert response_login.status_code == 401, "Expected status code 401 Unauthorized"

    # login with original password
    payload_login = {"email": email, "password": original_password}
    response_login = await client.post(f"{ACCOUNTS_URL}/login", json=payload_login)
    assert response_login.status_code == 401, "Expected status code 401 Unauthorized"
