import json
from collections.abc import Callable, Awaitable
from decimal import Decimal
from typing import Any

import pytest
import stripe
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.models import User, UserGroupEnum
from src.cart.models import CartItem, Cart
from src.core.config import get_settings
from src.movies.models import Movie
from src.orders.models import Order, OrderStatusEnum, OrderItem
from src.payments.models import PaymentItem, Payment

from tests.helpers import (
    FakeEmailSender,
    post_signed_webhook,
    build_stripe_event,
)

settings = get_settings()
WEBHOOK_URL = f"{settings.API_VERSION_PREFIX}/payments/webhook"


async def test_checkout_completed(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_cart: Callable[..., Awaitable[Cart]],
    create_cart_item: Callable[..., Awaitable[CartItem]],
    create_order: Callable[..., Awaitable[Order]],
    fake_email_sender: FakeEmailSender,
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1", price=Decimal("9.99"))
    movie_2 = await create_movie(name="Movie 2", price=Decimal("4.99"))
    movie_3 = await create_movie(name="Movie 3", price=Decimal("1.99"))

    cart = await create_cart(user_id=user.id)
    await create_cart_item(cart=cart, movie=movie_1)
    await create_cart_item(cart=cart, movie=movie_2)
    await create_cart_item(cart=cart, movie=movie_3)

    order = await create_order(
        user_id=user.id,
        movies=[movie_1, movie_2],
        status=OrderStatusEnum.PENDING,
        checkout_session_id="cs_test_1",
    )

    response = await post_signed_webhook(
        client=client,
        webhook_url=WEBHOOK_URL,
        event=build_stripe_event(
            order_id=order.id,
            amount=int(order.total_amount * 100),
            session_id="cs_test_1",
            payment_intent="pi_test_1",
        ),
    )
    assert response.status_code == 200, "Expected status code 200 OK"

    assert (
        await db_session.scalar(select(Order.status).where(Order.id == order.id))
        == OrderStatusEnum.PAID
    )

    payments = await db_session.execute(
        select(Payment.user_id, Payment.amount, Payment.external_payment_id).where(
            Payment.order_id == order.id
        )
    )
    assert payments.tuples().all() == [(user.id, Decimal("14.98"), "pi_test_1")]

    payment_items = await db_session.execute(
        select(OrderItem.movie_id, PaymentItem.price_at_payment)
        .join(PaymentItem.order_item)
        .order_by(OrderItem.movie_id)
    )
    assert payment_items.tuples().all() == [
        (movie_1.id, Decimal("9.99")),
        (movie_2.id, Decimal("4.99")),
    ]

    assert (
        await db_session.scalars(
            select(CartItem.movie_id).where(CartItem.cart_id == cart.id)
        )
    ).all() == [movie_3.id]

    assert len(fake_email_sender.sent_emails) == 1
    sent_email = fake_email_sender.sent_emails[0]
    assert sent_email.to == user.email
    assert str(order.id) in sent_email.subject
    assert str(order.id) in sent_email.body


async def test_checkout_completed_twice(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    fake_email_sender: FakeEmailSender,
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1", price=Decimal("9.99"))
    movie_2 = await create_movie(name="Movie 2", price=Decimal("4.99"))

    order = await create_order(
        user_id=user.id,
        movies=[movie_1, movie_2],
        status=OrderStatusEnum.PENDING,
        checkout_session_id="cs_test_1",
    )

    event = build_stripe_event(
        order_id=order.id,
        amount=int(order.total_amount * 100),
        session_id="cs_test_1",
        payment_intent="pi_test_1",
    )

    response_1 = await post_signed_webhook(
        client=client,
        webhook_url=WEBHOOK_URL,
        event=event,
    )
    assert response_1.status_code == 200, "Expected status code 200 OK"
    response_2 = await post_signed_webhook(
        client=client,
        webhook_url=WEBHOOK_URL,
        event=event,
    )
    assert response_2.status_code == 200, "Expected status code 200 OK"

    payments = await db_session.execute(
        select(Payment.user_id, Payment.amount, Payment.external_payment_id).where(
            Payment.order_id == order.id
        )
    )
    assert payments.tuples().all() == [(user.id, Decimal("14.98"), "pi_test_1")]

    assert len(fake_email_sender.sent_emails) == 1
    sent_email = fake_email_sender.sent_emails[0]
    assert sent_email.to == user.email
    assert str(order.id) in sent_email.subject
    assert str(order.id) in sent_email.body


async def test_wrong_signature(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    fake_email_sender: FakeEmailSender,
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1", price=Decimal("9.99"))
    movie_2 = await create_movie(name="Movie 2", price=Decimal("4.99"))

    order = await create_order(
        user_id=user.id,
        movies=[movie_1, movie_2],
        status=OrderStatusEnum.PENDING,
        checkout_session_id="cs_test_1",
    )

    event = build_stripe_event(
        order_id=order.id,
        amount=int(order.total_amount * 100),
        session_id="cs_test_1",
    )
    signature = stripe.WebhookSignature.generate_signature_header(
        json.dumps(event), "whsec_wrong"
    )

    response = await client.post(
        WEBHOOK_URL,
        content=json.dumps(event),
        headers={"Stripe-Signature": signature},
    )
    assert response.status_code == 400, "Expected status code 400 Bad Request"

    assert (
        await db_session.scalar(select(Order.status).where(Order.id == order.id))
        == OrderStatusEnum.PENDING
    )
    payments = await db_session.execute(
        select(Payment.user_id, Payment.amount, Payment.external_payment_id).where(
            Payment.order_id == order.id
        )
    )
    assert payments.all() == []
    assert len(fake_email_sender.sent_emails) == 0


async def test_missing_signature(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    fake_email_sender: FakeEmailSender,
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1", price=Decimal("9.99"))
    movie_2 = await create_movie(name="Movie 2", price=Decimal("4.99"))

    order = await create_order(
        user_id=user.id,
        movies=[movie_1, movie_2],
        status=OrderStatusEnum.PENDING,
        checkout_session_id="cs_test_1",
    )

    event = build_stripe_event(
        order_id=order.id,
        amount=int(order.total_amount * 100),
        session_id="cs_test_1",
    )

    response = await client.post(
        WEBHOOK_URL,
        content=json.dumps(event),
    )
    assert response.status_code == 400, "Expected status code 400 Bad Request"

    assert (
        await db_session.scalar(select(Order.status).where(Order.id == order.id))
        == OrderStatusEnum.PENDING
    )
    payments = await db_session.execute(
        select(Payment.user_id, Payment.amount, Payment.external_payment_id).where(
            Payment.order_id == order.id
        )
    )
    assert payments.all() == []
    assert len(fake_email_sender.sent_emails) == 0


async def test_body_not_valid_json(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    fake_email_sender: FakeEmailSender,
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1", price=Decimal("9.99"))
    movie_2 = await create_movie(name="Movie 2", price=Decimal("4.99"))

    order = await create_order(
        user_id=user.id,
        movies=[movie_1, movie_2],
        status=OrderStatusEnum.PENDING,
        checkout_session_id="cs_test_1",
    )

    signature = stripe.WebhookSignature.generate_signature_header(
        "not json", settings.STRIPE_WEBHOOK_SECRET
    )

    response = await client.post(
        WEBHOOK_URL,
        content="not json",
        headers={"Stripe-Signature": signature},
    )
    assert response.status_code == 400, "Expected status code 400 Bad Request"

    assert (
        await db_session.scalar(select(Order.status).where(Order.id == order.id))
        == OrderStatusEnum.PENDING
    )
    payments = await db_session.execute(
        select(Payment.user_id, Payment.amount, Payment.external_payment_id).where(
            Payment.order_id == order.id
        )
    )
    assert payments.all() == []
    assert len(fake_email_sender.sent_emails) == 0


async def test_other_event_type_ignored(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    fake_email_sender: FakeEmailSender,
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1", price=Decimal("9.99"))
    movie_2 = await create_movie(name="Movie 2", price=Decimal("4.99"))

    order = await create_order(
        user_id=user.id,
        movies=[movie_1, movie_2],
        status=OrderStatusEnum.PENDING,
        checkout_session_id="cs_test_1",
    )

    response = await post_signed_webhook(
        client=client,
        webhook_url=WEBHOOK_URL,
        event=build_stripe_event(
            event_type="payment_intent.created",
            order_id=order.id,
            amount=int(order.total_amount * 100),
            session_id="cs_test_1",
        ),
    )
    assert response.status_code == 200, "Expected status code 200 OK"

    assert (
        await db_session.scalar(select(Order.status).where(Order.id == order.id))
        == OrderStatusEnum.PENDING
    )
    payments = await db_session.execute(
        select(Payment.user_id, Payment.amount, Payment.external_payment_id).where(
            Payment.order_id == order.id
        )
    )
    assert payments.all() == []
    assert len(fake_email_sender.sent_emails) == 0


async def test_no_order_id_in_metadata(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    fake_email_sender: FakeEmailSender,
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1", price=Decimal("9.99"))
    movie_2 = await create_movie(name="Movie 2", price=Decimal("4.99"))

    order = await create_order(
        user_id=user.id,
        movies=[movie_1, movie_2],
        status=OrderStatusEnum.PENDING,
    )

    response = await post_signed_webhook(
        client=client,
        webhook_url=WEBHOOK_URL,
        event=build_stripe_event(
            order_id=None,
        ),
    )
    assert response.status_code == 200, "Expected status code 200 OK"

    assert (
        await db_session.scalar(select(Order.status).where(Order.id == order.id))
        == OrderStatusEnum.PENDING
    )
    payments = await db_session.execute(
        select(Payment.user_id, Payment.amount, Payment.external_payment_id).where(
            Payment.order_id == order.id
        )
    )
    assert payments.all() == []
    assert len(fake_email_sender.sent_emails) == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"payment_status": "unpaid"},
        {"session_id": "cs_test_other"},
        {"amount": 1},
        {"payment_intent": None},
    ],
    ids=["unpaid", "other_session", "wrong_amount", "no_payment_intent"],
)
async def test_checkout_completed_ignored(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    fake_email_sender: FakeEmailSender,
    overrides: dict[str, Any],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1", price=Decimal("9.99"))
    movie_2 = await create_movie(name="Movie 2", price=Decimal("4.99"))

    order = await create_order(
        user_id=user.id,
        movies=[movie_1, movie_2],
        status=OrderStatusEnum.PENDING,
        checkout_session_id="cs_test_1",
    )

    event = build_stripe_event(
        **{
            "order_id": order.id,
            "session_id": "cs_test_1",
            "amount": int(order.total_amount * 100),
            **overrides,
        },
    )
    response = await post_signed_webhook(
        client=client,
        webhook_url=WEBHOOK_URL,
        event=event,
    )
    assert response.status_code == 200, "Expected status code 200 OK"

    assert (
        await db_session.scalar(select(Order.status).where(Order.id == order.id))
        == OrderStatusEnum.PENDING
    )
    payments = await db_session.execute(
        select(Payment.user_id, Payment.amount, Payment.external_payment_id).where(
            Payment.order_id == order.id
        )
    )
    assert payments.all() == []
    assert len(fake_email_sender.sent_emails) == 0


async def test_unknown_order(
    client: AsyncClient,
    db_session: AsyncSession,
):
    response = await post_signed_webhook(
        client=client,
        webhook_url=WEBHOOK_URL,
        event=build_stripe_event(
            order_id=12345,
        ),
    )
    assert response.status_code == 200, "Expected status code 200 OK"

    payments = await db_session.execute(
        select(Payment.user_id, Payment.amount, Payment.external_payment_id)
    )
    assert payments.all() == []


async def test_canceled_order(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    fake_email_sender: FakeEmailSender,
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1", price=Decimal("9.99"))
    movie_2 = await create_movie(name="Movie 2", price=Decimal("4.99"))

    order = await create_order(
        user_id=user.id,
        movies=[movie_1, movie_2],
        status=OrderStatusEnum.CANCELED,
        checkout_session_id="cs_test_1",
    )

    response = await post_signed_webhook(
        client=client,
        webhook_url=WEBHOOK_URL,
        event=build_stripe_event(
            order_id=order.id,
            amount=int(order.total_amount * 100),
            session_id="cs_test_1",
        ),
    )
    assert response.status_code == 200, "Expected status code 200 OK"

    assert (
        await db_session.scalar(select(Order.status).where(Order.id == order.id))
        == OrderStatusEnum.CANCELED
    )
    payments = await db_session.execute(
        select(Payment.user_id, Payment.amount, Payment.external_payment_id).where(
            Payment.order_id == order.id
        )
    )
    assert payments.all() == []
    assert len(fake_email_sender.sent_emails) == 0
