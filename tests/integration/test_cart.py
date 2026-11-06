from collections.abc import Callable, Awaitable
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.accounts.models import UserGroupEnum
from src.accounts.models import User
from src.cart.models import CartItem, Cart
from src.core.config import get_settings
from src.movies.models import Movie
from src.orders.models import Order, OrderStatusEnum

from tests.helpers import auth_headers

settings = get_settings()
CART_URL = f"{settings.API_VERSION_PREFIX}/cart"


async def test_list_cart_items(
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

    movie_1 = await create_movie(name="Movie 1", year=2000, price=Decimal("9.99"))
    movie_2 = await create_movie(name="Movie 2")
    movie_3 = await create_movie(name="Movie 3")

    cart = await create_cart(user_id=user.id)
    cart_item_1 = await create_cart_item(cart=cart, movie=movie_1)
    await create_cart_item(cart=cart, movie=movie_2)
    await create_cart_item(cart=cart, movie=movie_3)

    response = await client.get(CART_URL, headers=auth_headers(user))
    assert response.status_code == 200, "Expected status code 200 OK"

    assert [item["movie"]["id"] for item in response.json()] == [
        movie_1.id,
        movie_2.id,
        movie_3.id,
    ]
    assert response.json()[0] == {
        "movie": {
            "id": movie_1.id,
            "name": "Movie 1",
            "year": 2000,
            "price": "9.99",
            "genres": [],
        },
        "added_at": cart_item_1.added_at.isoformat().replace("+00:00", "Z"),
    }


async def test_list_cart_items_with_no_cart(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    response = await client.get(CART_URL, headers=auth_headers(user))
    assert response.status_code == 200, "Expected status code 200 OK"

    assert (
        await db_session.scalar(select(exists().where(Cart.user_id == user.id)))
        is False
    ), "Cart was created"
    assert response.json() == []


async def test_another_user_items_are_not_shown_in_list(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_cart: Callable[..., Awaitable[Cart]],
    create_cart_item: Callable[..., Awaitable[CartItem]],
):
    current_user = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    another_user = await create_user(
        email="user2@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1", year=2000, price=Decimal("9.99"))
    movie_2 = await create_movie(name="Movie 2")

    cart_1 = await create_cart(user_id=current_user.id)
    cart_2 = await create_cart(user_id=another_user.id)

    await create_cart_item(cart=cart_1, movie=movie_1)
    await create_cart_item(cart=cart_2, movie=movie_2)

    response = await client.get(CART_URL, headers=auth_headers(current_user))
    assert response.status_code == 200, "Expected status code 200 OK"

    assert [item["movie"]["id"] for item in response.json()] == [movie_1.id]


async def test_create_cart_items(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    movie_1 = await create_movie(name="Movie 1")
    movie_2 = await create_movie(name="Movie 2")

    payload_1 = {"movie_id": movie_1.id}
    payload_2 = {"movie_id": movie_2.id}

    response_1 = await client.post(
        f"{CART_URL}/items", json=payload_1, headers=auth_headers(user)
    )
    assert response_1.status_code == 201, "Expected status code 201 Created"
    assert await db_session.scalar(
        select(exists().where(Cart.user_id == user.id))
    ), "Cart was not created"
    assert response_1.json()["movie"]["id"] == movie_1.id

    response_2 = await client.post(
        f"{CART_URL}/items", json=payload_2, headers=auth_headers(user)
    )
    assert response_2.status_code == 201, "Expected status code 201 Created"

    cart = await db_session.scalar(select(Cart).where(Cart.user_id == user.id))
    assert cart is not None
    result = await db_session.scalars(
        select(CartItem).where(CartItem.cart_id == cart.id)
    )
    items_in_cart = result.all()
    assert len(items_in_cart) == 2
    assert response_2.json()["movie"]["id"] == movie_2.id


async def test_create_duplicate_cart_item(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_cart: Callable[..., Awaitable[Cart]],
    create_cart_item: Callable[..., Awaitable[CartItem]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    movie = await create_movie(name="Movie 1")
    cart = await create_cart(user_id=user.id)
    await create_cart_item(cart=cart, movie=movie)
    payload = {"movie_id": movie.id}

    response = await client.post(
        f"{CART_URL}/items", json=payload, headers=auth_headers(user)
    )
    assert response.status_code == 409, "Expected status code 409 Conflict"


async def test_create_cart_item_with_purchased_movie(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie = await create_movie(name="Movie 1")
    await create_order(user_id=user.id, movies=[movie], status=OrderStatusEnum.PAID)
    payload = {"movie_id": movie.id}

    response = await client.post(
        f"{CART_URL}/items", json=payload, headers=auth_headers(user)
    )
    assert response.status_code == 409, "Expected status code 409 Conflict"
    assert (
        await db_session.scalar(select(exists().where(Cart.user_id == user.id)))
        is False
    )


async def test_create_cart_item_with_movie_in_pending_order(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_order: Callable[..., Awaitable[Order]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie = await create_movie(name="Movie 1")
    await create_order(user_id=user.id, movies=[movie], status=OrderStatusEnum.PENDING)
    payload = {"movie_id": movie.id}

    response = await client.post(
        f"{CART_URL}/items", json=payload, headers=auth_headers(user)
    )
    assert response.status_code == 201, "Expected status code 201 Created"


async def test_create_cart_item_with_unknown_movie(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    payload = {"movie_id": 12345}

    response = await client.post(
        f"{CART_URL}/items", json=payload, headers=auth_headers(user)
    )
    assert response.status_code == 404, "Expected status code 404 Not Found"


async def test_create_cart_item_unauthenticated(
    client: AsyncClient,
    create_movie: Callable[..., Awaitable[Movie]],
):
    movie = await create_movie(name="Movie 1")
    payload = {"movie_id": movie.id}

    response = await client.post(f"{CART_URL}/items", json=payload)
    assert response.status_code == 401, "Expected status code 401 Unauthorized"


async def test_delete_cart_item(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_cart: Callable[..., Awaitable[Cart]],
    create_cart_item: Callable[..., Awaitable[CartItem]],
):
    current_user = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    another_user = await create_user(
        email="user2@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    movie_1 = await create_movie(name="Movie 1")

    another_user_cart = await create_cart(user_id=another_user.id)
    current_user_cart = await create_cart(user_id=current_user.id)

    another_user_cart_item = await create_cart_item(
        cart=another_user_cart, movie=movie_1
    )
    current_user_cart_item = await create_cart_item(
        cart=current_user_cart, movie=movie_1
    )

    response = await client.delete(
        f"{CART_URL}/items/{movie_1.id}", headers=auth_headers(current_user)
    )
    assert response.status_code == 204, "Expected status code 204 No Content"

    assert (
        await db_session.scalar(
            select(exists().where(CartItem.id == current_user_cart_item.id))
        )
        is False
    ), "Item was not deleted from the cart"
    assert await db_session.scalar(
        select(exists().where(CartItem.id == another_user_cart_item.id))
    ), "Another user's item was deleted from the cart"


async def test_delete_cart_item_with_movie_not_in_cart(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_cart: Callable[..., Awaitable[Cart]],
):
    user = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    movie = await create_movie(name="Movie 1")
    await create_cart(user_id=user.id)

    response = await client.delete(
        f"{CART_URL}/items/{movie.id}", headers=auth_headers(user)
    )
    assert response.status_code == 404, "Expected status code 404 Not Found"


async def test_delete_cart_item_with_no_cart(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
):
    user = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    response = await client.delete(
        f"{CART_URL}/items/12345", headers=auth_headers(user)
    )
    assert response.status_code == 404, "Expected status code 404 Not Found"
    assert (
        await db_session.scalar(select(exists().where(Cart.user_id == user.id)))
        is False
    ), "Cart was created"


async def test_clear_cart(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_cart: Callable[..., Awaitable[Cart]],
    create_cart_item: Callable[..., Awaitable[CartItem]],
):
    current_user = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    another_user = await create_user(
        email="user2@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    movie_1 = await create_movie(name="Movie 1")
    movie_2 = await create_movie(name="Movie 2")
    movie_3 = await create_movie(name="Movie 3")

    cart_1 = await create_cart(user_id=current_user.id)
    cart_2 = await create_cart(user_id=another_user.id)

    await create_cart_item(cart=cart_1, movie=movie_1)
    await create_cart_item(cart=cart_1, movie=movie_2)
    cart_item_3 = await create_cart_item(cart=cart_2, movie=movie_3)

    response = await client.delete(CART_URL, headers=auth_headers(current_user))
    assert response.status_code == 204, "Expected status code 204 No Content"

    db_cart_1 = await db_session.scalar(
        select(Cart).where(Cart.id == cart_1.id).options(selectinload(Cart.items))
    )
    assert db_cart_1 is not None
    assert db_cart_1.items == []

    db_cart_2 = await db_session.scalar(
        select(Cart).where(Cart.id == cart_2.id).options(selectinload(Cart.items))
    )
    assert db_cart_2 is not None
    assert db_cart_2.items == [cart_item_3]


async def test_clear_cart_with_no_cart(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
):
    user = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    response = await client.delete(CART_URL, headers=auth_headers(user))
    assert response.status_code == 204, "Expected status code 204 No Content"
    assert (
        await db_session.scalar(select(exists().where(Cart.user_id == user.id)))
        is False
    ), "Cart was created"


async def test_list_cart_items_of_another_user_as_moderator(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_cart: Callable[..., Awaitable[Cart]],
    create_cart_item: Callable[..., Awaitable[CartItem]],
):
    moderator = await create_user(
        email="moderator@example.com",
        is_active=True,
        user_group=UserGroupEnum.MODERATOR,
    )
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    movie_1 = await create_movie(name="Movie 1")
    movie_2 = await create_movie(name="Movie 2")

    cart = await create_cart(user_id=user.id)
    await create_cart_item(cart=cart, movie=movie_1)
    await create_cart_item(cart=cart, movie=movie_2)

    response = await client.get(
        f"{CART_URL}/users/{user.id}", headers=auth_headers(moderator)
    )
    assert response.status_code == 200, "Expected status code 200 OK"
    assert [item["movie"]["id"] for item in response.json()] == [
        movie_1.id,
        movie_2.id,
    ]


async def test_list_cart_items_of_another_user_as_user(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
    create_cart: Callable[..., Awaitable[Cart]],
    create_cart_item: Callable[..., Awaitable[CartItem]],
):
    current_user = await create_user(
        email="user1@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    another_user = await create_user(
        email="user2@example.com", is_active=True, user_group=UserGroupEnum.USER
    )
    movie_1 = await create_movie(name="Movie 1")
    cart = await create_cart(user_id=another_user.id)
    await create_cart_item(cart=cart, movie=movie_1)

    response = await client.get(
        f"{CART_URL}/users/{another_user.id}", headers=auth_headers(current_user)
    )
    assert response.status_code == 403, "Expected status code 403 Forbidden"


async def test_list_cart_items_of_another_user_with_unknown_user(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    moderator = await create_user(
        email="moderator@example.com",
        is_active=True,
        user_group=UserGroupEnum.MODERATOR,
    )

    response = await client.get(
        f"{CART_URL}/users/12345", headers=auth_headers(moderator)
    )
    assert response.status_code == 404, "Expected status code 404 Not Found"


async def test_list_cart_items_of_another_user_with_no_cart_as_moderator(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    moderator = await create_user(
        email="moderator@example.com",
        is_active=True,
        user_group=UserGroupEnum.MODERATOR,
    )
    user = await create_user(
        email="user@example.com", is_active=True, user_group=UserGroupEnum.USER
    )

    response = await client.get(
        f"{CART_URL}/users/{user.id}", headers=auth_headers(moderator)
    )
    assert response.status_code == 200, "Expected status code 200 OK"
    assert response.json() == []
