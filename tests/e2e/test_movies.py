from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from src.accounts.models import User, UserGroupEnum
from src.core.config import get_settings
from tests.helpers import create_movie_payload

settings = get_settings()
ACCOUNTS_URL = f"{settings.API_VERSION_PREFIX}/accounts"
MOVIES_URL = f"{settings.API_VERSION_PREFIX}/movies"


async def test_moderator_adds_movies_and_visitor_browses_catalog(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
):
    email = "moderator@example.com"
    password = "Password12345!"
    await create_user(
        email=email,
        password=password,
        is_active=True,
        user_group=UserGroupEnum.MODERATOR,
    )

    # moderator creates genres and movies
    # moderator login
    payload_login = {"email": email, "password": password}
    response_login = await client.post(f"{ACCOUNTS_URL}/login", json=payload_login)
    assert response_login.status_code == 200, "Expected status code 200 OK"
    moderator_headers = {
        "Authorization": f"Bearer {response_login.json()['access_token']}"
    }

    # create a certification
    response_certification = await client.post(
        f"{MOVIES_URL}/certifications",
        json={"name": "Test Certification"},
        headers=moderator_headers,
    )
    assert response_certification.status_code == 201, "Expected status code 201 Created"
    certification_id = response_certification.json()["id"]

    # create genres
    response_genre_drama = await client.post(
        f"{MOVIES_URL}/genres",
        json={"name": "Drama"},
        headers=moderator_headers,
    )
    assert response_genre_drama.status_code == 201, "Expected status code 201 Created"
    drama_id = response_genre_drama.json()["id"]
    response_genre_comedy = await client.post(
        f"{MOVIES_URL}/genres",
        json={"name": "Comedy"},
        headers=moderator_headers,
    )
    assert response_genre_comedy.status_code == 201, "Expected status code 201 Created"
    comedy_id = response_genre_comedy.json()["id"]

    # create movies
    movie_ids = {}
    for name, imdb, genre_id in [
        ("Best Drama", 9.0, drama_id),
        ("Good Drama", 8.0, drama_id),
        ("Weak Drama", 6.0, drama_id),
        ("Best Comedy", 9.5, comedy_id),
    ]:
        movie_data = create_movie_payload(
            name=name,
            imdb=imdb,
            certification_id=certification_id,
            genre_ids=[genre_id],
        )
        response = await client.post(
            MOVIES_URL,
            json=movie_data,
            headers=moderator_headers,
        )
        assert response.status_code == 201, "Expected status code 201 Created"
        movie_ids[name] = response.json()["id"]

    # visitor browses the catalog (no auth)
    # list genres
    response_genres = await client.get(f"{MOVIES_URL}/genres")
    assert response_genres.status_code == 200, "Expected status code 200 OK"
    genres = {genre["name"]: genre for genre in response_genres.json()}
    drama = genres["Drama"]
    assert drama["movie_count"] == 3

    # filter movies
    response_movies = await client.get(
        MOVIES_URL,
        params={
            "genre_id": drama["id"],
            "min_imdb": 7,
            "sort_by": "imdb",
            "order": "desc",
            "page_size": 1,
        },
    )
    assert response_movies.status_code == 200, "Expected status code 200 OK"
    first_page = response_movies.json()
    assert first_page["total"] == 2
    assert len(first_page["items"]) == 1
    assert first_page["items"][0]["id"] == movie_ids["Best Drama"]
    movies_next_page = first_page["next_page"]

    # filter movies, next page
    response_movies = await client.get(movies_next_page)
    assert response_movies.status_code == 200, "Expected status code 200 OK"
    second_page = response_movies.json()
    assert len(second_page["items"]) == 1
    assert second_page["items"][0]["id"] == movie_ids["Good Drama"]
    assert second_page["next_page"] is None

    # movie details
    response_movie = await client.get(
        f"{MOVIES_URL}/{second_page["items"][0]["id"]}",
    )
    assert response_movie.status_code == 200, "Expected status code 200 OK"
    response_movie_data = response_movie.json()
    assert response_movie_data["name"] == "Good Drama"
    assert response_movie_data["description"] is not None
