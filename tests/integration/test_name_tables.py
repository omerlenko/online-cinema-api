from collections.abc import Callable, Awaitable

import pytest
from httpx import AsyncClient
from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.models import UserGroupEnum
from src.accounts.models import User
from src.core.config import get_settings
from src.movies.models import (
    Genre,
    Movie,
    UniqueNameBase,
    Star,
    Director,
    Certification,
)
from tests.helpers import auth_headers

settings = get_settings()
MOVIES_URL = f"{settings.API_VERSION_PREFIX}/movies"


FULL_CRUD_TABLES = [
    pytest.param("genres", Genre, id="genres"),
    pytest.param("stars", Star, id="stars"),
    pytest.param("directors", Director, id="directors"),
    pytest.param("certifications", Certification, id="certifications"),
]


@pytest.mark.parametrize("url_segment, model", FULL_CRUD_TABLES)
async def test_list(
    client: AsyncClient,
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
    url_segment: str,
    model: type[UniqueNameBase],
):
    object_1 = await create_unique_name_object(name="Drama", model=model)
    object_2 = await create_unique_name_object(name="Comedy", model=model)
    object_3 = await create_unique_name_object(name="Thriller", model=model)

    response = await client.get(f"{MOVIES_URL}/{url_segment}")
    assert response.status_code == 200, "Expected status code 200 OK"

    response_ids = [item["id"] for item in response.json()]
    assert response_ids == [
        object_1.id,
        object_2.id,
        object_3.id,
    ], "Expected ids are not in the response."
    assert response.json()[0]["id"] == object_1.id
    assert response.json()[0]["name"] == "Drama"


async def test_list_genres_movie_count(
    client: AsyncClient,
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
    create_movie: Callable[..., Awaitable[Movie]],
):
    genre_1 = await create_unique_name_object(name="Drama", model=Genre)
    genre_2 = await create_unique_name_object(name="Thriller", model=Genre)
    genre_3 = await create_unique_name_object(name="Comedy", model=Genre)
    await create_movie(name="Movie 1", genres=[genre_1])
    await create_movie(name="Movie 2", genres=[genre_2])

    response = await client.get(f"{MOVIES_URL}/genres")
    assert response.status_code == 200, "Expected status code 200 OK"
    assert response.json()[0] == {"id": genre_1.id, "name": "Drama", "movie_count": 1}
    assert response.json()[1] == {
        "id": genre_2.id,
        "name": "Thriller",
        "movie_count": 1,
    }
    assert response.json()[2] == {"id": genre_3.id, "name": "Comedy", "movie_count": 0}


@pytest.mark.parametrize("url_segment, model", FULL_CRUD_TABLES)
async def test_create_as_moderator(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    url_segment: str,
    model: type[UniqueNameBase],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    payload = {"name": "Drama"}

    response = await client.post(
        f"{MOVIES_URL}/{url_segment}", json=payload, headers=auth_headers(moderator)
    )
    assert response.status_code == 201, "Expected status code 201 Created"
    result = await db_session.scalars(select(model))
    objects = result.all()
    assert len(objects) == 1, "Expected exactly 1 object to exist"
    assert objects[0].name == payload["name"], f"Object name is not '{payload["name"]}'"


@pytest.mark.parametrize("url_segment, model", FULL_CRUD_TABLES)
async def test_create_as_user(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    url_segment: str,
    model: type[UniqueNameBase],
):
    user = await create_user(is_active=True, user_group=UserGroupEnum.USER)
    payload = {"name": "Drama"}

    response = await client.post(
        f"{MOVIES_URL}/{url_segment}", json=payload, headers=auth_headers(user)
    )
    assert response.status_code == 403, "Expected status code 403 Forbidden"


@pytest.mark.parametrize("url_segment, model", FULL_CRUD_TABLES)
async def test_create_with_duplicate_name(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
    url_segment: str,
    model: type[UniqueNameBase],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    await create_unique_name_object(name="Drama", model=model)
    payload = {"name": "Drama"}

    response = await client.post(
        f"{MOVIES_URL}/{url_segment}", json=payload, headers=auth_headers(moderator)
    )
    assert response.status_code == 409, "Expected status code 409 Conflict"


@pytest.mark.parametrize("url_segment, model", FULL_CRUD_TABLES)
async def test_update_with_taken_name(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
    url_segment: str,
    model: type[UniqueNameBase],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    await create_unique_name_object(name="Drama", model=model)
    object_to_update = await create_unique_name_object(name="Comedy", model=model)
    payload = {"name": "drama"}

    response = await client.put(
        f"{MOVIES_URL}/{url_segment}/{object_to_update.id}",
        json=payload,
        headers=auth_headers(moderator),
    )
    assert response.status_code == 409, "Expected status code 409 Conflict"


@pytest.mark.parametrize("url_segment, model", FULL_CRUD_TABLES)
async def test_update_change_name_case(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
    url_segment: str,
    model: type[UniqueNameBase],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    object_to_update = await create_unique_name_object(name="Drama", model=model)
    payload = {"name": "drama"}

    response = await client.put(
        f"{MOVIES_URL}/{url_segment}/{object_to_update.id}",
        json=payload,
        headers=auth_headers(moderator),
    )
    assert response.status_code == 200, "Expected status code 200 OK"
    assert response.json()["name"] == payload["name"], "Object name was not updated"


@pytest.mark.parametrize("url_segment, model", FULL_CRUD_TABLES)
async def test_update_with_unknown_object(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    url_segment: str,
    model: type[UniqueNameBase],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    payload = {"name": "drama"}

    response = await client.put(
        f"{MOVIES_URL}/{url_segment}/12345",
        json=payload,
        headers=auth_headers(moderator),
    )
    assert response.status_code == 404, "Expected status code 404 Not Found"


@pytest.mark.parametrize("url_segment, model", FULL_CRUD_TABLES)
async def test_delete(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
    url_segment: str,
    model: type[UniqueNameBase],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    object_to_delete = await create_unique_name_object(name="Drama", model=model)

    response = await client.delete(
        f"{MOVIES_URL}/{url_segment}/{object_to_delete.id}",
        headers=auth_headers(moderator),
    )
    assert response.status_code == 204, "Expected status code 204 No Content"
    assert (
        await db_session.scalar(
            select(exists().where(model.name == object_to_delete.name))
        )
        is False
    )


@pytest.mark.parametrize("url_segment, model", FULL_CRUD_TABLES)
async def test_delete_with_unknown_object(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    url_segment: str,
    model: type[UniqueNameBase],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)

    response = await client.delete(
        f"{MOVIES_URL}/{url_segment}/12345",
        headers=auth_headers(moderator),
    )
    assert response.status_code == 404, "Expected status code 404 Not Found"


@pytest.mark.parametrize(
    "url_segment, model, movie_field",
    [
        pytest.param("genres", Genre, "genres", id="genres"),
        pytest.param("stars", Star, "stars", id="stars"),
        pytest.param("directors", Director, "directors", id="directors"),
        pytest.param(
            "certifications", Certification, "certification_id", id="certifications"
        ),
    ],
)
async def test_delete_while_in_use(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
    create_movie: Callable[..., Awaitable[Movie]],
    url_segment: str,
    model: type[UniqueNameBase],
    movie_field: str,
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    obj = await create_unique_name_object(name="Drama", model=model)
    await create_movie(
        **{movie_field: obj.id if movie_field == "certification_id" else [obj]}
    )

    response = await client.delete(
        f"{MOVIES_URL}/{url_segment}/{obj.id}",
        headers=auth_headers(moderator),
    )
    assert response.status_code == 409, "Expected status code 409 Conflict"
    assert (
        await db_session.scalar(select(exists().where(model.name == obj.name))) is True
    )
