from collections.abc import Callable, Awaitable
from datetime import datetime, timezone
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select, exists, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.models import User, UserGroupEnum
from src.cart.models import CartItem, Cart
from src.core.config import get_settings
from src.movies.models import Movie
from src.orders.models import Order, OrderStatusEnum
from src.orders.schemas import ExcludedMovieReasonEnum

from tests.helpers import auth_headers

settings = get_settings()
ORDERS_URL = f"{settings.API_VERSION_PREFIX}/orders"


async def test_list_orders(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
):
    user = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    another_user = await create_user(
        email="user2@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1")
    movie_2 = await create_movie(name="Movie 2")
    movie_3 = await create_movie(name="Movie 3", price=Decimal("9.99"))

    order_1 = await create_order(
        user_id=user.id,
        movies=[movie_1],
        created_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    order_2 = await create_order(
        user_id=user.id,
        movies=[movie_2],
        created_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )
    order_3 = await create_order(
        user_id=user.id,
        movies=[movie_3],
        created_at=datetime(2026, 11, 3, tzinfo=timezone.utc),
    )
    await create_order(
        user_id=another_user.id,
        movies=[],
        created_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
    )

    response = await client.get(ORDERS_URL, headers=auth_headers(user))
    assert response.status_code == 200, "Expected status code 200 OK"

    assert [item["id"] for item in response.json()["items"]] == [
        order_3.id,
        order_2.id,
        order_1.id,
    ]
    assert response.json()["total"] == 3
    assert response.json()["items"][0] == {
        "id": order_3.id,
        "created_at": order_3.created_at.isoformat().replace("+00:00", "Z"),
        "status": "pending",
        "total_amount": "9.99",
        "items": [
            {"movie": {"id": movie_3.id, "name": "Movie 3"}, "price_at_order": "9.99"}
        ],
    }


async def test_list_orders_filter_by_status(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_order: Callable[..., Awaitable[Order]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    order_paid = await create_order(
        user_id=user.id, movies=[], status=OrderStatusEnum.PAID
    )
    await create_order(user_id=user.id, movies=[], status=OrderStatusEnum.PENDING)
    await create_order(user_id=user.id, movies=[], status=OrderStatusEnum.CANCELED)
    params = {"status": "paid"}

    response = await client.get(ORDERS_URL, params=params, headers=auth_headers(user))
    assert response.status_code == 200, "Expected status code 200 OK"

    assert [item["id"] for item in response.json()["items"]] == [order_paid.id]


async def test_list_orders_filter_by_date(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_order: Callable[..., Awaitable[Order]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    order_1 = await create_order(
        user_id=user.id,
        movies=[],
        created_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )
    order_2 = await create_order(
        user_id=user.id,
        movies=[],
        created_at=datetime(2026, 11, 3, hour=12, tzinfo=timezone.utc),
    )
    await create_order(
        user_id=user.id,
        movies=[],
        created_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    await create_order(
        user_id=user.id,
        movies=[],
        created_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
    )
    params = {"date_from": "2026-11-02", "date_to": "2026-11-03"}

    response = await client.get(ORDERS_URL, params=params, headers=auth_headers(user))
    assert response.status_code == 200, "Expected status code 200 OK"

    assert [item["id"] for item in response.json()["items"]] == [order_2.id, order_1.id]


async def test_list_orders_with_date_to_before_date_from(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    params = {"date_from": "2026-11-30", "date_to": "2026-11-01"}

    response = await client.get(ORDERS_URL, params=params, headers=auth_headers(user))
    assert response.status_code == 422, "Expected status code 422 Unprocessable Content"


async def test_list_orders_search(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Key Movie 1")
    movie_2 = await create_movie(name="Key Movie 2")
    movie_3 = await create_movie(name="Movie")

    order_1 = await create_order(
        user_id=user.id,
        movies=[movie_1],
        created_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    order_2 = await create_order(
        user_id=user.id,
        movies=[movie_2],
        created_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )
    await create_order(user_id=user.id, movies=[movie_3])
    params = {"search": "key"}

    response = await client.get(ORDERS_URL, params=params, headers=auth_headers(user))
    assert response.status_code == 200, "Expected status code 200 OK"

    assert [item["id"] for item in response.json()["items"]] == [
        order_2.id,
        order_1.id,
    ]


async def test_list_orders_sort_order(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1")
    movie_2 = await create_movie(name="Movie 2")
    movie_3 = await create_movie(name="Movie 3")

    order_1 = await create_order(
        user_id=user.id,
        movies=[movie_1],
        created_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    order_2 = await create_order(
        user_id=user.id,
        movies=[movie_2],
        created_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )
    order_3 = await create_order(
        user_id=user.id,
        movies=[movie_3],
        created_at=datetime(2026, 11, 3, tzinfo=timezone.utc),
    )
    params = {"sort_order": "asc"}

    response = await client.get(ORDERS_URL, params=params, headers=auth_headers(user))
    assert response.status_code == 200, "Expected status code 200 OK"

    assert [item["id"] for item in response.json()["items"]] == [
        order_1.id,
        order_2.id,
        order_3.id,
    ]


async def test_place_order(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_cart: Callable[..., Awaitable[Cart]],
    create_cart_item: Callable[..., Awaitable[CartItem]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1", price=Decimal("4.99"))
    movie_2 = await create_movie(name="Movie 2", price=Decimal("9.99"))

    cart = await create_cart(user_id=user.id)
    await create_cart_item(cart=cart, movie=movie_1)
    await create_cart_item(cart=cart, movie=movie_2)

    response = await client.post(ORDERS_URL, headers=auth_headers(user))
    assert response.status_code == 201, "Expected status code 201 Created"

    assert [
        (item["movie"]["id"], item["price_at_order"])
        for item in response.json()["order"]["items"]
    ] == [
        (movie_1.id, str(movie_1.price)),
        (movie_2.id, str(movie_2.price)),
    ]
    assert response.json()["order"]["status"] == "pending"
    assert response.json()["order"]["total_amount"] == str(
        movie_1.price + movie_2.price
    )
    assert response.json()["excluded_movies"] == []
    assert await db_session.scalar(select(exists().where(CartItem.cart_id == cart.id)))
    assert await db_session.scalar(select(exists().where(Order.user_id == user.id)))


async def test_place_order_with_no_cart(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    response = await client.post(ORDERS_URL, headers=auth_headers(user))
    assert response.status_code == 400, "Expected status code 400 Bad Request"


async def test_place_order_with_empty_cart(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_cart: Callable[..., Awaitable[Cart]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    await create_cart(user_id=user.id)

    response = await client.post(ORDERS_URL, headers=auth_headers(user))
    assert response.status_code == 400, "Expected status code 400 Bad Request"


async def test_place_order_with_mixed_cart(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_cart: Callable[..., Awaitable[Cart]],
    create_cart_item: Callable[..., Awaitable[CartItem]],
    create_order: Callable[..., Awaitable[Order]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_pending = await create_movie(name="Movie 1")
    movie_paid = await create_movie(name="Movie 2")
    movie_new = await create_movie(name="Movie 3")

    await create_order(
        user_id=user.id, movies=[movie_pending], status=OrderStatusEnum.PENDING
    )
    await create_order(
        user_id=user.id, movies=[movie_paid], status=OrderStatusEnum.PAID
    )

    cart = await create_cart(user_id=user.id)
    await create_cart_item(cart=cart, movie=movie_pending)
    await create_cart_item(cart=cart, movie=movie_paid)
    await create_cart_item(cart=cart, movie=movie_new)

    response = await client.post(ORDERS_URL, headers=auth_headers(user))
    assert response.status_code == 201, "Expected status code 201 Created"

    assert [item["movie"]["id"] for item in response.json()["order"]["items"]] == [
        movie_new.id
    ]
    assert [
        (movie["id"], movie["reason"]) for movie in response.json()["excluded_movies"]
    ] == [
        (movie_pending.id, ExcludedMovieReasonEnum.PENDING),
        (movie_paid.id, ExcludedMovieReasonEnum.PURCHASED),
    ]


async def test_place_order_everything_excluded(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_cart: Callable[..., Awaitable[Cart]],
    create_cart_item: Callable[..., Awaitable[CartItem]],
    create_order: Callable[..., Awaitable[Order]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_pending = await create_movie(name="Movie 1")
    movie_paid = await create_movie(name="Movie 2")

    await create_order(
        user_id=user.id, movies=[movie_pending], status=OrderStatusEnum.PENDING
    )
    await create_order(
        user_id=user.id, movies=[movie_paid], status=OrderStatusEnum.PAID
    )

    cart = await create_cart(user_id=user.id)
    await create_cart_item(cart=cart, movie=movie_pending)
    await create_cart_item(cart=cart, movie=movie_paid)

    response = await client.post(ORDERS_URL, headers=auth_headers(user))
    assert response.status_code == 409, "Expected status code 409 Conflict"
    assert await db_session.scalar(select(func.count(Order.id))) == 2


async def test_place_order_canceled_movie_not_excluded(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_cart: Callable[..., Awaitable[Cart]],
    create_cart_item: Callable[..., Awaitable[CartItem]],
    create_order: Callable[..., Awaitable[Order]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_canceled = await create_movie(name="Movie 1")

    await create_order(
        user_id=user.id, movies=[movie_canceled], status=OrderStatusEnum.CANCELED
    )

    cart = await create_cart(user_id=user.id)
    await create_cart_item(cart=cart, movie=movie_canceled)

    response = await client.post(ORDERS_URL, headers=auth_headers(user))
    assert response.status_code == 201, "Expected status code 201 Created"

    assert [item["movie"]["id"] for item in response.json()["order"]["items"]] == [
        movie_canceled.id
    ]


async def test_place_order_not_affected_by_other_users_orders(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_cart: Callable[..., Awaitable[Cart]],
    create_cart_item: Callable[..., Awaitable[CartItem]],
    create_order: Callable[..., Awaitable[Order]],
):
    current_user = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    another_user = await create_user(
        email="user2@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie = await create_movie(name="Movie 1")
    await create_order(
        user_id=another_user.id, movies=[movie], status=OrderStatusEnum.PAID
    )

    cart = await create_cart(user_id=current_user.id)
    await create_cart_item(cart=cart, movie=movie)

    response = await client.post(ORDERS_URL, headers=auth_headers(current_user))
    assert response.status_code == 201, "Expected status code 201 Created"
    assert [item["movie"]["id"] for item in response.json()["order"]["items"]] == [
        movie.id
    ]
    assert response.json()["excluded_movies"] == []


async def test_place_order_unauthenticated(
    client: AsyncClient,
):
    response = await client.post(ORDERS_URL)
    assert response.status_code == 401, "Expected status code 401 Unauthorized"


async def test_order_details(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1", price=Decimal("4.99"))
    movie_2 = await create_movie(name="Movie 2", price=Decimal("4.99"))

    order = await create_order(
        user_id=user.id, movies=[movie_1, movie_2], status=OrderStatusEnum.PENDING
    )

    response = await client.get(f"{ORDERS_URL}/{order.id}", headers=auth_headers(user))
    assert response.status_code == 200, "Expected status code 200 OK"
    assert response.json() == {
        "id": order.id,
        "created_at": order.created_at.isoformat().replace("+00:00", "Z"),
        "status": "pending",
        "total_amount": "9.98",
        "items": [
            {"movie": {"id": movie_1.id, "name": "Movie 1"}, "price_at_order": "4.99"},
            {"movie": {"id": movie_2.id, "name": "Movie 2"}, "price_at_order": "4.99"},
        ],
    }


async def test_order_details_another_users_order(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
):
    current_user = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    another_user = await create_user(
        email="user2@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie = await create_movie(name="Movie 1")
    order = await create_order(
        user_id=another_user.id, movies=[movie], status=OrderStatusEnum.PAID
    )

    response = await client.get(
        f"{ORDERS_URL}/{order.id}", headers=auth_headers(current_user)
    )
    assert response.status_code == 404, "Expected status code 404 Not Found"


async def test_order_details_unknown_order(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    response = await client.get(f"{ORDERS_URL}/12345", headers=auth_headers(user))
    assert response.status_code == 404, "Expected status code 404 Not Found"


async def test_cancel_order(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_order: Callable[..., Awaitable[Order]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    order = await create_order(
        user_id=user.id, movies=[], status=OrderStatusEnum.PENDING
    )

    response = await client.post(
        f"{ORDERS_URL}/{order.id}/cancel", headers=auth_headers(user)
    )
    assert response.status_code == 200, "Expected status code 200 OK"
    assert response.json()["status"] == "canceled"
    db_order_status = await db_session.scalar(
        select(Order.status).where(Order.id == order.id)
    )
    assert db_order_status == OrderStatusEnum.CANCELED


async def test_cancel_order_with_canceled_order(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_order: Callable[..., Awaitable[Order]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    canceled_order = await create_order(
        user_id=user.id, movies=[], status=OrderStatusEnum.CANCELED
    )

    response = await client.post(
        f"{ORDERS_URL}/{canceled_order.id}/cancel", headers=auth_headers(user)
    )
    assert response.status_code == 200, "Expected status code 200 OK"
    assert response.json()["status"] == "canceled"
    db_order_status = await db_session.scalar(
        select(Order.status).where(Order.id == canceled_order.id)
    )
    assert db_order_status == OrderStatusEnum.CANCELED


async def test_cancel_order_with_paid_order(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_order: Callable[..., Awaitable[Order]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    paid_order = await create_order(
        user_id=user.id, movies=[], status=OrderStatusEnum.PAID
    )

    response = await client.post(
        f"{ORDERS_URL}/{paid_order.id}/cancel", headers=auth_headers(user)
    )
    assert response.status_code == 409, "Expected status code 409 Conflict"
    db_order_status = await db_session.scalar(
        select(Order.status).where(Order.id == paid_order.id)
    )
    assert db_order_status == OrderStatusEnum.PAID


async def test_cancel_order_with_another_users_order(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_order: Callable[..., Awaitable[Order]],
):
    current_user = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    another_user = await create_user(
        email="user2@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    order = await create_order(
        user_id=another_user.id, movies=[], status=OrderStatusEnum.PENDING
    )

    response = await client.post(
        f"{ORDERS_URL}/{order.id}/cancel", headers=auth_headers(current_user)
    )
    assert response.status_code == 404, "Expected status code 404 Not Found"
    db_order_status = await db_session.scalar(
        select(Order.status).where(Order.id == order.id)
    )
    assert db_order_status == OrderStatusEnum.PENDING


async def test_list_all_orders_as_user(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_order: Callable[..., Awaitable[Order]],
):
    user = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    another_user = await create_user(
        email="user2@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    await create_order(user_id=another_user.id, movies=[])

    response = await client.get(f"{ORDERS_URL}/all", headers=auth_headers(user))
    assert response.status_code == 403, "Expected status code 403 Forbidden"


async def test_list_all_orders_as_moderator(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_order: Callable[..., Awaitable[Order]],
):
    moderator = await create_user(
        email="moderator@example.com",
        is_active=True,
        user_group=UserGroupEnum.MODERATOR,
    )
    user_1 = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    user_2 = await create_user(
        email="user2@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    order_1 = await create_order(
        user_id=user_1.id,
        movies=[],
        created_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    order_2 = await create_order(
        user_id=user_2.id,
        movies=[],
        created_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )

    response = await client.get(f"{ORDERS_URL}/all", headers=auth_headers(moderator))
    assert response.status_code == 200, "Expected status code 200 OK"
    assert [(item["id"], item["user_id"]) for item in response.json()["items"]] == [
        (order_2.id, user_2.id),
        (order_1.id, user_1.id),
    ]
    assert response.json()["total"] == 2


async def test_list_all_orders_filter_by_user(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_order: Callable[..., Awaitable[Order]],
):
    moderator = await create_user(
        email="moderator@example.com",
        is_active=True,
        user_group=UserGroupEnum.MODERATOR,
    )
    user_1 = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    user_2 = await create_user(
        email="user2@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    order_1 = await create_order(
        user_id=user_1.id,
        movies=[],
        created_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    order_2 = await create_order(
        user_id=user_1.id,
        movies=[],
        created_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )
    await create_order(
        user_id=user_2.id,
        movies=[],
        created_at=datetime(2026, 11, 3, tzinfo=timezone.utc),
    )
    await create_order(
        user_id=user_2.id,
        movies=[],
        created_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
    )

    params = {"user_id": user_1.id}
    response = await client.get(
        f"{ORDERS_URL}/all", params=params, headers=auth_headers(moderator)
    )
    assert response.status_code == 200, "Expected status code 200 OK"
    assert [item["id"] for item in response.json()["items"]] == [
        order_2.id,
        order_1.id,
    ]
    assert response.json()["total"] == 2
