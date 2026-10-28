from collections.abc import Callable, Awaitable

import pytest
from httpx import AsyncClient
from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

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
from src.movies.schemas import MovieSeedSchema
from src.movies.seed import seed_movie
from tests.helpers import auth_headers, create_movie_payload, seed_movie_payload

settings = get_settings()
MOVIES_URL = f"{settings.API_VERSION_PREFIX}/movies"


async def test_create_movie_as_moderator(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    certification = await create_unique_name_object(name="R", model=Certification)
    genre = await create_unique_name_object(name="Thriller", model=Genre)
    star_1 = await create_unique_name_object(name="Brad Pitt", model=Star)
    star_2 = await create_unique_name_object(name="Morgan Freeman", model=Star)
    director = await create_unique_name_object(name="David Fincher", model=Director)

    payload = create_movie_payload(
        certification_id=certification.id,
        genre_ids=[genre.id],
        star_ids=[star_1.id, star_2.id],
        director_ids=[director.id],
    )

    response = await client.post(
        MOVIES_URL, json=payload, headers=auth_headers(moderator)
    )
    assert response.status_code == 201, "Expected status code 201 Created"
    result = await db_session.scalars(select(Movie))
    movies = result.all()
    assert len(movies) == 1, "Expected exactly 1 movie to exist"
    assert movies[0].name == payload["name"], f"Movie name is not '{payload["name"]}'"


async def test_create_movie_as_user(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
):
    user = await create_user(is_active=True, user_group=UserGroupEnum.USER)
    certification = await create_unique_name_object(name="R", model=Certification)

    payload = create_movie_payload(
        certification_id=certification.id,
    )

    response = await client.post(MOVIES_URL, json=payload, headers=auth_headers(user))
    assert response.status_code == 403, "Expected status code 403 Forbidden"
    assert (
        await db_session.scalar(select(exists().where(Movie.name == payload["name"])))
        is False
    )


async def test_create_movie_with_unknown_genre(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    certification = await create_unique_name_object(name="R", model=Certification)
    genre = await create_unique_name_object(name="Thriller", model=Genre)
    missing_genre_id = 12345

    payload = create_movie_payload(
        certification_id=certification.id,
        genre_ids=[genre.id, missing_genre_id],
    )

    response = await client.post(
        MOVIES_URL, json=payload, headers=auth_headers(moderator)
    )
    assert response.status_code == 400, "Expected status code 400 Bad Request"
    assert (
        response.json()["detail"]
        == f"Genres with these ids not found: [{missing_genre_id}]"
    )


async def test_create_movie_with_unknown_certification(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    payload = create_movie_payload(
        certification_id=12345,
    )

    response = await client.post(
        MOVIES_URL, json=payload, headers=auth_headers(moderator)
    )
    assert response.status_code == 400, "Expected status code 400 Bad Request"


async def test_create_duplicate_movie(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
    create_movie: Callable[..., Awaitable[Movie]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    certification = await create_unique_name_object(name="R", model=Certification)
    existing_movie = await create_movie(
        name="Existing Movie", year=2000, time=120, certification_id=certification.id
    )
    payload = create_movie_payload(
        certification_id=certification.id,
        name="Existing Movie",
        year=2000,
        time=120,
    )

    response = await client.post(
        MOVIES_URL, json=payload, headers=auth_headers(moderator)
    )
    assert response.status_code == 409, "Expected status code 409 Conflict"
    result = await db_session.scalars(select(Movie))
    movies = result.all()
    assert len(movies) == 1, "Expected exactly 1 movie to exist"
    assert movies[0].id == existing_movie.id, "Expected movie is not in the database"


async def test_get_movie_details(
    client: AsyncClient,
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
    create_movie: Callable[..., Awaitable[Movie]],
):
    certification = await create_unique_name_object(name="R", model=Certification)
    genre = await create_unique_name_object(name="Thriller", model=Genre)
    star_1 = await create_unique_name_object(name="Brad Pitt", model=Star)
    star_2 = await create_unique_name_object(name="Morgan Freeman", model=Star)
    director = await create_unique_name_object(name="David Fincher", model=Director)
    movie = await create_movie(
        certification_id=certification.id,
        genres=[genre],
        stars=[star_1, star_2],
        directors=[director],
    )

    response = await client.get(f"{MOVIES_URL}/{movie.id}")
    assert response.status_code == 200, "Expected status code 200 OK"
    assert response.json()["id"] == movie.id, "Movie id not in the response body"
    assert (
        response.json()["certification"]["name"] == certification.name
    ), "Certification name not in the response body"
    assert [genre["name"] for genre in response.json()["genres"]] == [
        genre.name
    ], "Expected genre names not in the response body"
    assert [star["name"] for star in response.json()["stars"]] == [
        star_1.name,
        star_2.name,
    ], "Expected star names not in the response body"
    assert [director["name"] for director in response.json()["directors"]] == [
        director.name
    ], "Expected director names not in the response body"


async def test_get_unknown_movie(
    client: AsyncClient,
):
    response = await client.get(f"{MOVIES_URL}/12345")
    assert response.status_code == 404, "Expected status code 404 Not Found"


async def test_list_movies(
    client: AsyncClient,
    create_movie: Callable[..., Awaitable[Movie]],
):
    movie_1 = await create_movie(name="Movie 1")
    movie_2 = await create_movie(name="Movie 2")
    movie_3 = await create_movie(name="Movie 3")

    response = await client.get(MOVIES_URL)
    assert response.status_code == 200, "Expected status code 200 OK"
    response_ids = [item["id"] for item in response.json()["items"]]
    assert response_ids == [
        movie_1.id,
        movie_2.id,
        movie_3.id,
    ], "Expected ids are not in the response."


async def test_list_movies_filter_by_year(
    client: AsyncClient,
    create_movie: Callable[..., Awaitable[Movie]],
):
    movie_1 = await create_movie(name="Movie 1", year=1995)
    movie_2 = await create_movie(name="Movie 2", year=2000)
    await create_movie(name="Movie 3", year=1994)
    await create_movie(name="Movie 4", year=2001)

    query_params = {"year_from": 1995, "year_to": 2000}

    response = await client.get(MOVIES_URL, params=query_params)
    assert response.status_code == 200, "Expected status code 200 OK"
    response_ids = [item["id"] for item in response.json()["items"]]
    assert response_ids == [
        movie_1.id,
        movie_2.id,
    ], "Expected ids are not in the response."
    assert response.json()["total"] == 2, "Total items counter is not correct."


async def test_list_movies_filter_by_min_imdb(
    client: AsyncClient,
    create_movie: Callable[..., Awaitable[Movie]],
):
    movie_1 = await create_movie(name="Movie 1", imdb=7)
    movie_2 = await create_movie(name="Movie 2", imdb=7.5)
    await create_movie(name="Movie 3", imdb=6.5)

    query_params = {"min_imdb": 7}

    response = await client.get(MOVIES_URL, params=query_params)
    assert response.status_code == 200, "Expected status code 200 OK"
    response_ids = [item["id"] for item in response.json()["items"]]
    assert response_ids == [
        movie_1.id,
        movie_2.id,
    ], "Expected ids are not in the response."


async def test_list_movies_filter_by_min_meta_score(
    client: AsyncClient,
    create_movie: Callable[..., Awaitable[Movie]],
):
    movie_1 = await create_movie(name="Movie 1", meta_score=67)
    movie_2 = await create_movie(name="Movie 2", meta_score=69)
    movie_3 = await create_movie(name="Movie 3", meta_score=60)
    await create_movie(name="Movie 4", meta_score=50)

    query_params = {"min_meta_score": 60}

    response = await client.get(MOVIES_URL, params=query_params)
    assert response.status_code == 200, "Expected status code 200 OK"
    response_ids = [item["id"] for item in response.json()["items"]]
    assert response_ids == [
        movie_1.id,
        movie_2.id,
        movie_3.id,
    ], "Expected ids are not in the response."


async def test_list_movies_filter_by_genre(
    client: AsyncClient,
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
    create_movie: Callable[..., Awaitable[Movie]],
):
    genre_1 = await create_unique_name_object(name="Drama", model=Genre)
    genre_2 = await create_unique_name_object(name="Thriller", model=Genre)
    movie_1 = await create_movie(name="Movie 1", genres=[genre_1])
    movie_2 = await create_movie(name="Movie 2", genres=[genre_1, genre_2])
    await create_movie(name="Movie 3", genres=[genre_2])

    query_params = {"genre_id": genre_1.id}

    response = await client.get(MOVIES_URL, params=query_params)
    assert response.status_code == 200, "Expected status code 200 OK"
    response_ids = [item["id"] for item in response.json()["items"]]
    assert response_ids == [
        movie_1.id,
        movie_2.id,
    ], "Expected ids are not in the response."


async def test_list_movies_search(
    client: AsyncClient,
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
    create_movie: Callable[..., Awaitable[Movie]],
):
    genre = await create_unique_name_object(name="Keyword Genre", model=Genre)
    star = await create_unique_name_object(name="Keyword Star", model=Star)
    director = await create_unique_name_object(name="Keyword Director", model=Director)
    movie_1 = await create_movie(
        name="Keyword",
    )
    movie_2 = await create_movie(name="Movie 2", description="Keyword")
    movie_3 = await create_movie(name="Movie 3", genres=[genre])
    movie_4 = await create_movie(name="Movie 4", stars=[star])
    movie_5 = await create_movie(name="Movie 5", directors=[director])
    await create_movie(
        name="Movie 6", description="Movie", genres=[], stars=[], directors=[]
    )

    query_params = {"search": "key"}

    response = await client.get(MOVIES_URL, params=query_params)
    assert response.status_code == 200, "Expected status code 200 OK"
    response_ids = [item["id"] for item in response.json()["items"]]
    assert response_ids == [
        movie_1.id,
        movie_2.id,
        movie_3.id,
        movie_4.id,
        movie_5.id,
    ], "Expected ids are not in the response."


async def test_list_movies_sort_by_meta_score_ascending(
    client: AsyncClient,
    create_movie: Callable[..., Awaitable[Movie]],
):
    movie_1 = await create_movie(name="Movie 1")
    movie_2 = await create_movie(name="Movie 2", meta_score=30)
    movie_3 = await create_movie(name="Movie 3")
    movie_4 = await create_movie(name="Movie 4", meta_score=90)
    movie_5 = await create_movie(name="Movie 5", meta_score=60)

    query_params = {"sort_by": "meta_score"}

    response = await client.get(MOVIES_URL, params=query_params)
    assert response.status_code == 200, "Expected status code 200 OK"
    response_ids = [item["id"] for item in response.json()["items"]]
    assert response_ids == [
        movie_2.id,
        movie_5.id,
        movie_4.id,
        movie_1.id,
        movie_3.id,
    ], "IDs are not in the expected order."


async def test_list_movies_sort_by_meta_score_descending(
    client: AsyncClient,
    create_movie: Callable[..., Awaitable[Movie]],
):
    movie_1 = await create_movie(name="Movie 1")
    movie_2 = await create_movie(name="Movie 2", meta_score=30)
    movie_3 = await create_movie(name="Movie 3")
    movie_4 = await create_movie(name="Movie 4", meta_score=90)
    movie_5 = await create_movie(name="Movie 5", meta_score=60)

    query_params = {"sort_by": "meta_score", "order": "desc"}

    response = await client.get(MOVIES_URL, params=query_params)
    assert response.status_code == 200, "Expected status code 200 OK"
    response_ids = [item["id"] for item in response.json()["items"]]
    assert response_ids == [
        movie_4.id,
        movie_5.id,
        movie_2.id,
        movie_1.id,
        movie_3.id,
    ], "IDs are not in the expected order."


async def test_list_movies_pagination(
    client: AsyncClient,
    create_movie: Callable[..., Awaitable[Movie]],
):
    await create_movie(name="Movie 1")
    await create_movie(name="Movie 2")
    await create_movie(name="Movie 3")

    query_params = {"page": 1, "page_size": 1}
    response = await client.get(MOVIES_URL, params=query_params)
    assert response.status_code == 200, "Expected status code 200 OK"
    assert response.json()["total"] == 3, "Total items counter is not correct."
    assert response.json()["previous_page"] is None
    assert "?page=2&page_size=1" in response.json()["next_page"]

    query_params = {"page": 2, "page_size": 1}
    response = await client.get(MOVIES_URL, params=query_params)
    assert response.status_code == 200, "Expected status code 200 OK"
    assert "?page=1&page_size=1" in response.json()["previous_page"]
    assert "?page=3&page_size=1" in response.json()["next_page"]

    query_params = {"page": 3, "page_size": 1}
    response = await client.get(MOVIES_URL, params=query_params)
    assert response.status_code == 200, "Expected status code 200 OK"
    assert "?page=2&page_size=1" in response.json()["previous_page"]
    assert response.json()["next_page"] is None


async def test_delete_movie(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    movie = await create_movie()

    response = await client.delete(
        f"{MOVIES_URL}/{movie.id}", headers=auth_headers(moderator)
    )
    assert response.status_code == 204, "Expected status code 204 No Content"
    assert (
        await db_session.scalar(select(exists().where(Movie.id == movie.id))) is False
    ), "Movie was not deleted from the database"


async def test_delete_unknown_movie(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)

    response = await client.delete(
        f"{MOVIES_URL}/12345", headers=auth_headers(moderator)
    )
    assert response.status_code == 404, "Expected status code 404 Not Found"


async def test_update_movie_plain_field(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    movie = await create_movie(name="Old Name")
    payload = {"name": "New Name"}

    response = await client.patch(
        f"{MOVIES_URL}/{movie.id}", json=payload, headers=auth_headers(moderator)
    )
    assert response.status_code == 200, "Expected status code 200 OK"
    assert response.json()["name"] == payload["name"], "Movie name was not updated"


async def test_update_movie_certification(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
    create_movie: Callable[..., Awaitable[Movie]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    old_certification = await create_unique_name_object(name="R", model=Certification)
    new_certification = await create_unique_name_object(
        name="PG-13", model=Certification
    )
    movie = await create_movie(certification_id=old_certification.id)

    payload = {"certification_id": new_certification.id}

    response = await client.patch(
        f"{MOVIES_URL}/{movie.id}", json=payload, headers=auth_headers(moderator)
    )
    assert response.status_code == 200, "Expected status code 200 OK"
    assert (
        response.json()["certification"]["id"] == new_certification.id
    ), "Movie certification was not updated"


async def test_update_movie_linked_field(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
    create_movie: Callable[..., Awaitable[Movie]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    star_1 = await create_unique_name_object(name="Brad Pitt", model=Star)
    star_2 = await create_unique_name_object(name="Morgan Freeman", model=Star)
    star_3 = await create_unique_name_object(name="Kevin Spacey", model=Star)
    movie = await create_movie(stars=[star_1, star_2])

    payload = {"star_ids": [star_2.id, star_3.id]}

    response = await client.patch(
        f"{MOVIES_URL}/{movie.id}", json=payload, headers=auth_headers(moderator)
    )
    assert response.status_code == 200, "Expected status code 200 OK"
    assert [star["id"] for star in response.json()["stars"]] == [
        star_2.id,
        star_3.id,
    ], "Expected ids are not in the response"


async def test_update_movie_delete_linked_field(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
    create_movie: Callable[..., Awaitable[Movie]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    star_1 = await create_unique_name_object(name="Brad Pitt", model=Star)
    star_2 = await create_unique_name_object(name="Morgan Freeman", model=Star)
    star_3 = await create_unique_name_object(name="Kevin Spacey", model=Star)
    movie = await create_movie(stars=[star_1, star_2, star_3])

    payload: dict[str, list[int]] = {"star_ids": []}

    response = await client.patch(
        f"{MOVIES_URL}/{movie.id}", json=payload, headers=auth_headers(moderator)
    )
    assert response.status_code == 200, "Expected status code 200 OK"
    assert response.json()["stars"] == [], "Linked stars were not cleared"


async def test_update_movie_duplicate(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    movie_to_change = await create_movie(name="Name To Change", year=1999, time=90)
    await create_movie(name="Existing Name", year=2000, time=120)
    payload = {"name": "Existing Name", "year": 2000, "time": 120}

    response = await client.patch(
        f"{MOVIES_URL}/{movie_to_change.id}",
        json=payload,
        headers=auth_headers(moderator),
    )
    assert response.status_code == 409, "Expected status code 409 Conflict"


async def test_update_unknown_movie(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    payload = {"name": "New Name"}

    response = await client.patch(
        f"{MOVIES_URL}/12345",
        json=payload,
        headers=auth_headers(moderator),
    )
    assert response.status_code == 404, "Expected status code 404 Not Found"


async def test_update_movie_with_none_name(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_movie: Callable[..., Awaitable[Movie]],
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    movie = await create_movie(name="Test Name")
    payload = {
        "name": None,
    }

    response = await client.patch(
        f"{MOVIES_URL}/{movie.id}",
        json=payload,
        headers=auth_headers(moderator),
    )
    assert response.status_code == 200, "Expected status code 200 OK"
    assert response.json()["name"] == "Test Name", "Movie name was changed"


@pytest.mark.parametrize(
    "field, value",
    [("year", 1800), ("imdb", 11), ("price", -1), ("time", 0), ("meta_score", 101)],
)
async def test_create_movie_invalid_inputs(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
    field: str,
    value: int,
):
    moderator = await create_user(is_active=True, user_group=UserGroupEnum.MODERATOR)
    certification = await create_unique_name_object(name="R", model=Certification)
    payload = create_movie_payload(certification_id=certification.id)
    payload[field] = value

    response = await client.post(
        MOVIES_URL, json=payload, headers=auth_headers(moderator)
    )
    assert response.status_code == 422, "Expected status code 422 Unprocessable Content"


async def test_seed_movie(
    db_session: AsyncSession,
    create_unique_name_object: Callable[..., Awaitable[UniqueNameBase]],
):
    await create_unique_name_object(name="Drama", model=Genre)
    movie_data = MovieSeedSchema.model_validate(
        seed_movie_payload(genres=["Crime", "drama"])
    )

    await seed_movie(db=db_session, movie_data=movie_data)

    created_movie = await db_session.scalar(
        select(Movie)
        .where(Movie.name == movie_data.name)
        .options(
            joinedload(Movie.certification),
            selectinload(Movie.genres),
            selectinload(Movie.stars),
            selectinload(Movie.directors),
        )
    )
    assert created_movie is not None
    assert created_movie.certification.name == movie_data.certification

    assert {genre.name for genre in created_movie.genres} == {"Crime", "Drama"}
    assert {star.name for star in created_movie.stars} == set(movie_data.stars)
    assert {director.name for director in created_movie.directors} == set(
        movie_data.directors
    )


async def test_seed_movie_skips_existing_movie(
    db_session: AsyncSession,
):
    movie_data = MovieSeedSchema.model_validate(seed_movie_payload())

    assert await seed_movie(db=db_session, movie_data=movie_data) is True
    assert await seed_movie(db=db_session, movie_data=movie_data) is False

    created_movies = await db_session.scalars(select(Movie))
    assert len(created_movies.all()) == 1
