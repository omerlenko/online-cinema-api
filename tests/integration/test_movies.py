from collections.abc import Callable, Awaitable

from httpx import AsyncClient
from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.models import UserGroupEnum
from src.accounts.models import User
from src.core.config import get_settings
from src.movies.models import Genre, Movie
from tests.helpers import auth_headers

settings = get_settings()
MOVIES_URL = f"{settings.API_VERSION_PREFIX}/movies"


async def test_list_genres(
    client: AsyncClient, create_genre: Callable[..., Awaitable[Genre]]
):
    genre_1 = await create_genre(name="Drama")
    genre_2 = await create_genre(name="Comedy")
    genre_3 = await create_genre(name="Thriller")

    response = await client.get(f"{MOVIES_URL}/genres")
    assert response.status_code == 200, "Expected status code 200 OK"

    response_ids = [item["id"] for item in response.json()]
    assert response_ids == [
        genre_1.id,
        genre_2.id,
        genre_3.id,
    ], "Expected ids are not in the response."
    assert response.json()[0] == {
        "id": genre_1.id,
        "name": "Drama",
    }, "Response does not have the expected structure."


async def test_create_genre_as_moderator(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    payload = {"name": "Drama"}

    response = await client.post(
        f"{MOVIES_URL}/genres", json=payload, headers=auth_headers(moderator)
    )
    assert response.status_code == 201, "Expected status code 201 Created"
    result = await db_session.scalars(select(Genre))
    genres = result.all()
    assert len(genres) == 1, "Expected exactly 1 genre to exist"
    assert genres[0].name == payload["name"], "Genre name is not 'Drama'"


async def test_create_genre_as_user(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    user = await create_user(is_active=True, user_group=UserGroupEnum.USER)
    payload = {"name": "Drama"}

    response = await client.post(
        f"{MOVIES_URL}/genres", json=payload, headers=auth_headers(user)
    )
    assert response.status_code == 403, "Expected status code 403 Forbidden"


async def test_create_genre_with_duplicate_name(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_genre: Callable[..., Awaitable[Genre]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    await create_genre(name="Drama")
    payload = {"name": "Drama"}

    response = await client.post(
        f"{MOVIES_URL}/genres", json=payload, headers=auth_headers(moderator)
    )
    assert response.status_code == 409, "Expected status code 409 Conflict"


async def test_update_genre_with_taken_name(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_genre: Callable[..., Awaitable[Genre]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    await create_genre(name="Drama")
    genre_comedy = await create_genre(name="Comedy")
    payload = {"name": "drama"}

    response = await client.put(
        f"{MOVIES_URL}/genres/{genre_comedy.id}",
        json=payload,
        headers=auth_headers(moderator),
    )
    assert response.status_code == 409, "Expected status code 409 Conflict"


async def test_update_genre_change_name_case(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_genre: Callable[..., Awaitable[Genre]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    genre_drama = await create_genre(name="Drama")
    payload = {"name": "drama"}

    response = await client.put(
        f"{MOVIES_URL}/genres/{genre_drama.id}",
        json=payload,
        headers=auth_headers(moderator),
    )
    assert response.status_code == 200, "Expected status code 200 OK"
    assert response.json()["name"] == payload["name"], "Genre name was not updated"


async def test_update_genre_with_unknown_genre(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    payload = {"name": "drama"}

    response = await client.put(
        f"{MOVIES_URL}/genres/12345",
        json=payload,
        headers=auth_headers(moderator),
    )
    assert response.status_code == 404, "Expected status code 404 Not Found"


async def test_delete_genre(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_genre: Callable[..., Awaitable[Genre]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    genre = await create_genre(name="Drama")

    response = await client.delete(
        f"{MOVIES_URL}/genres/{genre.id}",
        headers=auth_headers(moderator),
    )
    assert response.status_code == 204, "Expected status code 204 No Content"
    assert (
        await db_session.scalar(select(exists().where(Genre.name == genre.name)))
        is False
    )


async def test_delete_genre_while_in_use(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_genre: Callable[..., Awaitable[Genre]],
    create_movie: Callable[..., Awaitable[Movie]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    genre = await create_genre(name="Drama")
    await create_movie(genres=[genre])

    response = await client.delete(
        f"{MOVIES_URL}/genres/{genre.id}",
        headers=auth_headers(moderator),
    )
    assert response.status_code == 409, "Expected status code 409 Conflict"
    assert (
        await db_session.scalar(select(exists().where(Genre.name == genre.name)))
        is True
    )


async def test_delete_genre_with_unknown_genre(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_genre: Callable[..., Awaitable[Genre]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)

    response = await client.delete(
        f"{MOVIES_URL}/genres/12345",
        headers=auth_headers(moderator),
    )
    assert response.status_code == 404, "Expected status code 404 Not Found"
