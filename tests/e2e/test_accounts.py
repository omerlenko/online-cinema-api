from urllib.parse import urlparse, parse_qs

from httpx import AsyncClient

from src.core.config import get_settings
from tests.helpers import FakeEmailSender

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
