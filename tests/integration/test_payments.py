from collections.abc import Callable, Awaitable
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.payments.gateway import CheckoutItem
from src.accounts.models import User, UserGroupEnum
from src.core.config import get_settings
from src.movies.models import Movie
from src.orders.models import Order, OrderStatusEnum, OrderItem
from src.payments.models import Payment, PaymentStatusEnum

from tests.helpers import auth_headers, FakeStripeGateway

settings = get_settings()
ORDERS_URL = f"{settings.API_VERSION_PREFIX}/orders"
PAYMENTS_URL = f"{settings.API_VERSION_PREFIX}/payments"


async def test_checkout(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    fake_stripe_gateway: FakeStripeGateway,
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    movie = await create_movie(name="Movie 1", price=Decimal("9.99"))
    order = await create_order(user_id=user.id, movies=[movie])

    response = await client.post(
        f"{ORDERS_URL}/{order.id}/checkout", headers=auth_headers(user)
    )
    assert response.status_code == 200, "Expected status code 200 OK"
    assert (
        response.json()["checkout_url"] == "https://checkout.stripe.test/cs_test_fake_1"
    )
    assert (
        await db_session.scalar(
            select(Order.checkout_session_id).where(Order.id == order.id)
        )
        == "cs_test_fake_1"
    )
    assert fake_stripe_gateway.created_sessions == [
        (order.id, [CheckoutItem(name=movie.name, price=movie.price)])
    ]
    assert fake_stripe_gateway.expired_session_ids == []


async def test_checkout_twice(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    fake_stripe_gateway: FakeStripeGateway,
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    movie = await create_movie(name="Movie 1", price=Decimal("9.99"))
    order = await create_order(user_id=user.id, movies=[movie])

    response_1 = await client.post(
        f"{ORDERS_URL}/{order.id}/checkout", headers=auth_headers(user)
    )
    assert response_1.status_code == 200, "Expected status code 200 OK"
    response_2 = await client.post(
        f"{ORDERS_URL}/{order.id}/checkout", headers=auth_headers(user)
    )
    assert response_2.status_code == 200, "Expected status code 200 OK"

    assert fake_stripe_gateway.expired_session_ids == ["cs_test_fake_1"]
    assert (
        await db_session.scalar(
            select(Order.checkout_session_id).where(Order.id == order.id)
        )
        == "cs_test_fake_2"
    )


async def test_checkout_previous_session_already_paid(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    fake_stripe_gateway: FakeStripeGateway,
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    movie = await create_movie(name="Movie 1", price=Decimal("9.99"))
    order = await create_order(user_id=user.id, movies=[movie])

    response_1 = await client.post(
        f"{ORDERS_URL}/{order.id}/checkout", headers=auth_headers(user)
    )
    assert response_1.status_code == 200, "Expected status code 200 OK"

    fake_stripe_gateway.session_paid = True
    response_2 = await client.post(
        f"{ORDERS_URL}/{order.id}/checkout", headers=auth_headers(user)
    )
    assert response_2.status_code == 409, "Expected status code 409 Conflict"

    assert fake_stripe_gateway.expired_session_ids == ["cs_test_fake_1"]
    assert (
        await db_session.scalar(
            select(Order.checkout_session_id).where(Order.id == order.id)
        )
        == "cs_test_fake_1"
    )
    assert len(fake_stripe_gateway.created_sessions) == 1


async def test_checkout_price_changed(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    fake_stripe_gateway: FakeStripeGateway,
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    movie = await create_movie(name="Movie 1", price=Decimal("9.99"))
    order = await create_order(user_id=user.id, movies=[movie])

    movie.price = Decimal("12.99")
    await db_session.flush()

    response = await client.post(
        f"{ORDERS_URL}/{order.id}/checkout", headers=auth_headers(user)
    )
    assert response.status_code == 409, "Expected status code 409 Conflict"

    assert await db_session.scalar(
        select(OrderItem.price_at_order).where(OrderItem.movie_id == movie.id)
    ) == Decimal("12.99")
    assert await db_session.scalar(
        select(Order.total_amount).where(Order.id == order.id)
    ) == Decimal("12.99")
    assert fake_stripe_gateway.created_sessions == []


async def test_checkout_again_after_price_changed(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    fake_stripe_gateway: FakeStripeGateway,
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    movie = await create_movie(name="Movie 1", price=Decimal("9.99"))
    order = await create_order(user_id=user.id, movies=[movie])

    movie.price = Decimal("12.99")
    await db_session.flush()

    response_1 = await client.post(
        f"{ORDERS_URL}/{order.id}/checkout", headers=auth_headers(user)
    )
    assert response_1.status_code == 409, "Expected status code 409 Conflict"
    response_2 = await client.post(
        f"{ORDERS_URL}/{order.id}/checkout", headers=auth_headers(user)
    )
    assert response_2.status_code == 200, "Expected status code 200 OK"

    assert fake_stripe_gateway.created_sessions == [
        (order.id, [CheckoutItem(name=movie.name, price=Decimal("12.99"))])
    ]


@pytest.mark.parametrize("status", [OrderStatusEnum.PAID, OrderStatusEnum.CANCELED])
async def test_checkout_order_status_is_not_pending(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    fake_stripe_gateway: FakeStripeGateway,
    status: OrderStatusEnum,
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    movie = await create_movie(name="Movie 1", price=Decimal("9.99"))
    order = await create_order(
        user_id=user.id,
        movies=[movie],
        status=status,
    )

    response = await client.post(
        f"{ORDERS_URL}/{order.id}/checkout", headers=auth_headers(user)
    )
    assert response.status_code == 409, "Expected status code 409 Conflict"
    assert fake_stripe_gateway.created_sessions == []


async def test_checkout_another_users_order(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    fake_stripe_gateway: FakeStripeGateway,
):
    current_user = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    another_user = await create_user(
        email="user2@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie = await create_movie(name="Movie 1", price=Decimal("9.99"))
    order = await create_order(user_id=another_user.id, movies=[movie])

    response = await client.post(
        f"{ORDERS_URL}/{order.id}/checkout", headers=auth_headers(current_user)
    )
    assert response.status_code == 404, "Expected status code 404 Not Found"
    assert fake_stripe_gateway.created_sessions == []


async def test_checkout_unknown_order(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    fake_stripe_gateway: FakeStripeGateway,
):
    user = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    response = await client.post(
        f"{ORDERS_URL}/12345/checkout", headers=auth_headers(user)
    )
    assert response.status_code == 404, "Expected status code 404 Not Found"
    assert fake_stripe_gateway.created_sessions == []


@pytest.mark.parametrize(
    "price, status_code",
    [
        (Decimal("0.49"), 400),
        (Decimal("0.50"), 200),
    ],
)
async def test_checkout_order_minimum_total_amount(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    fake_stripe_gateway: FakeStripeGateway,
    price: Decimal,
    status_code: int,
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    movie = await create_movie(name="Movie 1", price=price)
    order = await create_order(user_id=user.id, movies=[movie])

    response = await client.post(
        f"{ORDERS_URL}/{order.id}/checkout", headers=auth_headers(user)
    )
    assert response.status_code == status_code


async def test_checkout_with_payment_provider_down(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    fake_stripe_gateway: FakeStripeGateway,
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    movie = await create_movie(name="Movie 1", price=Decimal("9.99"))
    order = await create_order(user_id=user.id, movies=[movie])

    fake_stripe_gateway.provider_down = True
    response = await client.post(
        f"{ORDERS_URL}/{order.id}/checkout", headers=auth_headers(user)
    )
    assert response.status_code == 502, "Expected status code 502 Bad Gateway"
    assert (
        await db_session.scalar(
            select(Order.checkout_session_id).where(Order.id == order.id)
        )
        is None
    )


async def test_checkout_unauthenticated(
    client: AsyncClient,
):
    response = await client.post(f"{ORDERS_URL}/12345/checkout")
    assert response.status_code == 401, "Expected status code 401 Unauthorized"


async def test_payment_success_page(
    client: AsyncClient,
):
    response = await client.get(f"{PAYMENTS_URL}/success")
    assert response.status_code == 200, "Expected status code 200 OK"
    assert (
        response.json()["message"] == "Payment received. "
        "Your order will be marked as paid once the payment is confirmed."
    )


async def test_payment_success_page_order_status_is_not_changed(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    movie = await create_movie(name="Movie 1", price=Decimal("9.99"))
    order = await create_order(user_id=user.id, movies=[movie])

    response = await client.post(
        f"{ORDERS_URL}/{order.id}/checkout", headers=auth_headers(user)
    )
    assert response.status_code == 200, "Expected status code 200 OK"

    response = await client.get(
        f"{PAYMENTS_URL}/success", params={"session_id": "cs_test_fake_1"}
    )
    assert response.status_code == 200, "Expected status code 200 OK"

    assert (
        await db_session.scalar(select(Order.status).where(Order.id == order.id))
        == OrderStatusEnum.PENDING
    )


async def test_payment_cancel_page(
    client: AsyncClient,
):
    response = await client.get(f"{PAYMENTS_URL}/cancel")
    assert response.status_code == 200, "Expected status code 200 OK"
    assert (
        response.json()["message"] == "Payment was not completed. "
        "You can try again, or use a different payment method."
    )


async def test_list_payments(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    create_payment: Callable[..., Awaitable[Payment]],
):
    user_a = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    user_b = await create_user(
        email="user2@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1")
    order_1 = await create_order(
        user_id=user_a.id, movies=[movie_1], status=OrderStatusEnum.PAID
    )
    payment_1 = await create_payment(
        order=order_1, created_at=datetime(2026, 11, 1, tzinfo=timezone.utc)
    )

    movie_2 = await create_movie(name="Movie 2", price=Decimal("9.99"))
    order_2 = await create_order(
        user_id=user_a.id, movies=[movie_2], status=OrderStatusEnum.PAID
    )
    payment_2 = await create_payment(
        order=order_2, created_at=datetime(2026, 11, 2, tzinfo=timezone.utc)
    )

    movie_3 = await create_movie(name="Movie 3")
    order_3 = await create_order(
        user_id=user_b.id, movies=[movie_3], status=OrderStatusEnum.PAID
    )
    await create_payment(
        order=order_3, created_at=datetime(2026, 11, 3, tzinfo=timezone.utc)
    )

    response = await client.get(f"{PAYMENTS_URL}", headers=auth_headers(user_a))
    assert response.status_code == 200, "Expected status code 200 OK"

    assert [payment["id"] for payment in response.json()["items"]] == [
        payment_2.id,
        payment_1.id,
    ]
    assert response.json()["total"] == 2
    assert response.json()["items"][0] == {
        "id": payment_2.id,
        "created_at": payment_2.created_at.isoformat().replace("+00:00", "Z"),
        "status": "successful",
        "amount": "9.99",
        "order_id": order_2.id,
        "items": [
            {"movie": {"id": movie_2.id, "name": "Movie 2"}, "price_at_payment": "9.99"}
        ],
    }


async def test_list_payments_filter_by_status(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    create_payment: Callable[..., Awaitable[Payment]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1")
    order_1 = await create_order(
        user_id=user.id, movies=[movie_1], status=OrderStatusEnum.CANCELED
    )
    payment_1 = await create_payment(order=order_1, status=PaymentStatusEnum.REFUNDED)

    movie_2 = await create_movie(name="Movie 2")
    order_2 = await create_order(
        user_id=user.id, movies=[movie_2], status=OrderStatusEnum.PAID
    )
    await create_payment(order=order_2, status=PaymentStatusEnum.SUCCESSFUL)

    params = {"status": "refunded"}
    response = await client.get(
        f"{PAYMENTS_URL}", headers=auth_headers(user), params=params
    )
    assert response.status_code == 200, "Expected status code 200 OK"

    assert [payment["id"] for payment in response.json()["items"]] == [
        payment_1.id,
    ]
    assert response.json()["total"] == 1


async def test_list_payments_filter_by_date(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_order: Callable[..., Awaitable[Order]],
    create_payment: Callable[..., Awaitable[Payment]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    order_1 = await create_order(
        user_id=user.id, movies=[], status=OrderStatusEnum.PAID
    )
    await create_payment(
        order=order_1, created_at=datetime(2026, 11, 1, tzinfo=timezone.utc)
    )

    order_2 = await create_order(
        user_id=user.id, movies=[], status=OrderStatusEnum.PAID
    )
    payment_2 = await create_payment(
        order=order_2, created_at=datetime(2026, 11, 2, tzinfo=timezone.utc)
    )

    order_3 = await create_order(
        user_id=user.id, movies=[], status=OrderStatusEnum.PAID
    )
    payment_3 = await create_payment(
        order=order_3, created_at=datetime(2026, 11, 3, tzinfo=timezone.utc)
    )

    order_4 = await create_order(
        user_id=user.id, movies=[], status=OrderStatusEnum.PAID
    )
    await create_payment(
        order=order_4, created_at=datetime(2026, 11, 4, tzinfo=timezone.utc)
    )

    params = {"date_from": "2026-11-02", "date_to": "2026-11-03"}
    response = await client.get(
        f"{PAYMENTS_URL}", headers=auth_headers(user), params=params
    )
    assert response.status_code == 200, "Expected status code 200 OK"

    assert [payment["id"] for payment in response.json()["items"]] == [
        payment_3.id,
        payment_2.id,
    ]


async def test_list_payments_filter_invalid_date(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    params = {"date_from": "2026-11-04", "date_to": "2026-11-01"}
    response = await client.get(
        f"{PAYMENTS_URL}", headers=auth_headers(user), params=params
    )
    assert response.status_code == 422, "Expected status code 422 Unprocessable Content"


async def test_list_all_payments_as_admin(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    create_payment: Callable[..., Awaitable[Payment]],
):
    admin = await create_user(
        email="admin@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )
    user_a = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    user_b = await create_user(
        email="user2@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1")
    order_1 = await create_order(
        user_id=user_a.id, movies=[movie_1], status=OrderStatusEnum.PAID
    )
    payment_1 = await create_payment(order=order_1, status=PaymentStatusEnum.SUCCESSFUL)

    movie_2 = await create_movie(name="Movie 2", price=Decimal("9.99"))
    order_2 = await create_order(
        user_id=user_b.id, movies=[movie_2], status=OrderStatusEnum.CANCELED
    )
    payment_2 = await create_payment(order=order_2, status=PaymentStatusEnum.REFUNDED)

    response = await client.get(f"{PAYMENTS_URL}/all", headers=auth_headers(admin))
    assert response.status_code == 200, "Expected status code 200 OK"

    assert [payment["id"] for payment in response.json()["items"]] == [
        payment_2.id,
        payment_1.id,
    ]
    assert response.json()["total"] == 2
    assert response.json()["items"][0] == {
        "id": payment_2.id,
        "created_at": payment_2.created_at.isoformat().replace("+00:00", "Z"),
        "status": "refunded",
        "amount": "9.99",
        "order_id": order_2.id,
        "items": [
            {"movie": {"id": movie_2.id, "name": "Movie 2"}, "price_at_payment": "9.99"}
        ],
        "user_id": user_b.id,
    }


async def test_list_all_payments_filter_by_user_id(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    create_payment: Callable[..., Awaitable[Payment]],
):
    admin = await create_user(
        email="admin@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )
    user_a = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    user_b = await create_user(
        email="user2@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1")
    order_1 = await create_order(
        user_id=user_a.id, movies=[movie_1], status=OrderStatusEnum.PAID
    )
    payment_1 = await create_payment(order=order_1, status=PaymentStatusEnum.SUCCESSFUL)

    movie_2 = await create_movie(name="Movie 2")
    order_2 = await create_order(
        user_id=user_b.id, movies=[movie_2], status=OrderStatusEnum.CANCELED
    )
    await create_payment(order=order_2, status=PaymentStatusEnum.REFUNDED)

    params = {"user_id": user_a.id}
    response = await client.get(
        f"{PAYMENTS_URL}/all", headers=auth_headers(admin), params=params
    )
    assert response.status_code == 200, "Expected status code 200 OK"

    assert [payment["id"] for payment in response.json()["items"]] == [
        payment_1.id,
    ]
    assert response.json()["total"] == 1


async def test_list_all_payments_as_user(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    response = await client.get(f"{PAYMENTS_URL}/all", headers=auth_headers(user))
    assert response.status_code == 403, "Expected status code 403 Forbidden"


async def test_refund_payment_as_admin(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    create_payment: Callable[..., Awaitable[Payment]],
    fake_stripe_gateway: FakeStripeGateway,
):
    admin = await create_user(
        email="admin@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie = await create_movie(name="Movie 1")
    order = await create_order(
        user_id=user.id, movies=[movie], status=OrderStatusEnum.PAID
    )
    payment = await create_payment(order=order, status=PaymentStatusEnum.SUCCESSFUL)

    response = await client.post(
        f"{PAYMENTS_URL}/{payment.id}/refund", headers=auth_headers(admin)
    )
    assert response.status_code == 202, "Expected status code 202 Accepted"

    assert fake_stripe_gateway.refunded_payments == [payment.external_payment_id]
    assert (
        await db_session.scalar(select(Payment.status).where(Payment.id == payment.id))
        == PaymentStatusEnum.SUCCESSFUL
    )
    assert (
        await db_session.scalar(select(Order.status).where(Order.id == order.id))
        == OrderStatusEnum.PAID
    )


async def test_refund_payment_as_moderator(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_order: Callable[..., Awaitable[Order]],
    create_payment: Callable[..., Awaitable[Payment]],
    fake_stripe_gateway: FakeStripeGateway,
):
    moderator = await create_user(
        email="mod@example.com", is_active=True, user_group=UserGroupEnum.MODERATOR
    )
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    order = await create_order(user_id=user.id, movies=[], status=OrderStatusEnum.PAID)
    payment = await create_payment(order=order, status=PaymentStatusEnum.SUCCESSFUL)

    response = await client.post(
        f"{PAYMENTS_URL}/{payment.id}/refund", headers=auth_headers(moderator)
    )
    assert response.status_code == 403, "Expected status code 403 Forbidden"

    assert fake_stripe_gateway.refunded_payments == []


async def test_refund_payment_with_unknown_payment(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    admin = await create_user(
        email="admin@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )

    response = await client.post(
        f"{PAYMENTS_URL}/12345/refund", headers=auth_headers(admin)
    )
    assert response.status_code == 404, "Expected status code 404 Not Found"


async def test_refund_already_refunded_payment(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    create_payment: Callable[..., Awaitable[Payment]],
    fake_stripe_gateway: FakeStripeGateway,
):
    admin = await create_user(
        email="admin@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie = await create_movie(name="Movie 1")
    order = await create_order(
        user_id=user.id, movies=[movie], status=OrderStatusEnum.CANCELED
    )
    payment = await create_payment(order=order, status=PaymentStatusEnum.REFUNDED)

    response = await client.post(
        f"{PAYMENTS_URL}/{payment.id}/refund", headers=auth_headers(admin)
    )
    assert response.status_code == 409, "Expected status code 409 Conflict"

    assert fake_stripe_gateway.refunded_payments == []


async def test_refund_already_refunded_payment_in_stripe(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    create_payment: Callable[..., Awaitable[Payment]],
    fake_stripe_gateway: FakeStripeGateway,
):
    fake_stripe_gateway.already_refunded = True

    admin = await create_user(
        email="admin@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie = await create_movie(name="Movie 1")
    order = await create_order(
        user_id=user.id, movies=[movie], status=OrderStatusEnum.PAID
    )
    payment = await create_payment(order=order, status=PaymentStatusEnum.SUCCESSFUL)

    response = await client.post(
        f"{PAYMENTS_URL}/{payment.id}/refund", headers=auth_headers(admin)
    )
    assert response.status_code == 409, "Expected status code 409 Conflict"

    assert fake_stripe_gateway.refunded_payments == [payment.external_payment_id]


async def test_refund_payment_stripe_not_available(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
    create_payment: Callable[..., Awaitable[Payment]],
    fake_stripe_gateway: FakeStripeGateway,
):
    fake_stripe_gateway.provider_down = True

    admin = await create_user(
        email="admin@example.com", is_active=True, user_group=UserGroupEnum.ADMIN
    )
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie = await create_movie(name="Movie 1")
    order = await create_order(
        user_id=user.id, movies=[movie], status=OrderStatusEnum.PAID
    )
    payment = await create_payment(order=order, status=PaymentStatusEnum.SUCCESSFUL)

    response = await client.post(
        f"{PAYMENTS_URL}/{payment.id}/refund", headers=auth_headers(admin)
    )
    assert response.status_code == 502, "Expected status code 502 Bad Gateway"
