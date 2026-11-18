from collections.abc import Awaitable
from decimal import Decimal
from typing import Callable
from urllib.parse import urlparse, parse_qs

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.movies.models import Movie
from src.core.config import get_settings
from src.orders.models import Order
from src.payments.gateway import CheckoutItem
from tests.helpers import (
    FakeEmailSender,
    FakeStripeGateway,
    post_signed_webhook,
    build_stripe_event,
)

settings = get_settings()
ACCOUNTS_URL = f"{settings.API_VERSION_PREFIX}/accounts"
MOVIES_URL = f"{settings.API_VERSION_PREFIX}/movies"
CART_URL = f"{settings.API_VERSION_PREFIX}/cart"
ORDERS_URL = f"{settings.API_VERSION_PREFIX}/orders"
PAYMENTS_URL = f"{settings.API_VERSION_PREFIX}/payments"


async def test_place_order_and_purchase(
    client: AsyncClient,
    db_session: AsyncSession,
    create_movie: Callable[..., Awaitable[Movie]],
    fake_email_sender: FakeEmailSender,
    fake_stripe_gateway: FakeStripeGateway,
):
    movie_1 = await create_movie(name="Movie 1", price=Decimal("9.99"))
    movie_2 = await create_movie(name="Movie 2", price=Decimal("4.99"))

    # register
    email = "user@example.com"
    payload_register = {
        "email": email,
        "password": "Password12345!",
    }
    response_register = await client.post(
        f"{ACCOUNTS_URL}/register", json=payload_register
    )
    assert response_register.status_code == 201, "Expected status code 201 Created"

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
    access_token = response_login.json()["access_token"]
    auth_header = {"Authorization": f"Bearer {access_token}"}

    # add movie 1 to cart
    payload_add_movie_1 = {"movie_id": movie_1.id}
    response_add_movie_1 = await client.post(
        f"{CART_URL}/items", json=payload_add_movie_1, headers=auth_header
    )
    assert response_add_movie_1.status_code == 201, "Expected status code 201 Created"

    # add movie 2 to cart
    payload_add_movie_2 = {"movie_id": movie_2.id}
    response_add_movie_2 = await client.post(
        f"{CART_URL}/items", json=payload_add_movie_2, headers=auth_header
    )
    assert response_add_movie_2.status_code == 201, "Expected status code 201 Created"

    # place an order
    response_place_order = await client.post(ORDERS_URL, headers=auth_header)
    assert response_place_order.status_code == 201, "Expected status code 201 Created"
    order_id = response_place_order.json()["order"]["id"]

    # check out order
    response_checkout = await client.post(
        f"{ORDERS_URL}/{order_id}/checkout", headers=auth_header
    )
    assert response_checkout.status_code == 200, "Expected status code 200 OK"
    assert response_checkout.json()["checkout_url"] is not None
    assert fake_stripe_gateway.created_sessions == [
        (
            order_id,
            [
                CheckoutItem(name=movie_1.name, price=movie_1.price),
                CheckoutItem(name=movie_2.name, price=movie_2.price),
            ],
        )
    ]
    session_id = await db_session.scalar(
        select(Order.checkout_session_id).where(Order.id == order_id)
    )
    assert session_id is not None

    # send signed completed.checkout event to webhook
    event = build_stripe_event(session_id=session_id, order_id=order_id, amount=1498)
    response_webhook = await post_signed_webhook(
        client=client, webhook_url=f"{PAYMENTS_URL}/webhook", event=event
    )
    assert response_webhook.status_code == 200, "Expected status code 200 OK"

    # order details shows "paid" status
    response_order_details = await client.get(
        f"{ORDERS_URL}/{order_id}", headers=auth_header
    )
    assert response_order_details.status_code == 200, "Expected status code 200 OK"
    assert response_order_details.json()["status"] == "paid"

    # cart is empty
    response_cart = await client.get(CART_URL, headers=auth_header)
    assert response_cart.status_code == 200, "Expected status code 200 OK"
    assert response_cart.json() == []

    # 'purchased movies' shows both movies from the order
    response_purchased_movies = await client.get(
        f"{MOVIES_URL}/purchased", headers=auth_header
    )
    assert response_purchased_movies.status_code == 200, "Expected status code 200 OK"
    assert [movie["id"] for movie in response_purchased_movies.json()["items"]] == [
        movie_1.id,
        movie_2.id,
    ]

    # purchase confirmation email arrived
    assert len(fake_email_sender.sent_emails) == 2
    sent_email = fake_email_sender.sent_emails[-1]
    assert sent_email.to == email
    assert str(order_id) in sent_email.subject
    assert str(order_id) in sent_email.body

    # adding purchased movie back to cart returns 409
    payload_add_purchased_movie = {"movie_id": movie_1.id}
    response_add_purchased_movie = await client.post(
        f"{CART_URL}/items", json=payload_add_purchased_movie, headers=auth_header
    )
    assert (
        response_add_purchased_movie.status_code == 409
    ), "Expected status code 409 Conflict"
