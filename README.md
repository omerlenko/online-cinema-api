# Online Cinema API

[![CI](https://github.com/omerlenko/online-cinema-api/actions/workflows/ci-pipeline.yml/badge.svg?branch=main)](https://github.com/omerlenko/online-cinema-api/actions/workflows/ci-pipeline.yml)

Backend API for an online cinema platform where users can browse, purchase, and watch movies. Built with FastAPI and
async SQLAlchemy.

> 🚧 In active development.

## Features

### Accounts

- Registration with email and password (password complexity rules enforced)
- Email activation with a link valid for 24 hours
- Resending the activation link, without revealing whether an email is registered
- Login with JWT access and refresh tokens
- Refreshing the access token, and logout that revokes the refresh token
- Current user endpoint (`/accounts/me`)
- Password change for logged-in users, and password reset via an emailed, single-use token
- Periodic cleanup of expired activation, refresh and password reset tokens
- User groups (user, moderator, admin) with permission checks on protected endpoints
- Admin endpoints to list users (with filters, search, sorting and pagination), activate accounts manually and change a
  user's group
- Command to create the first admin account

### Movies

- Public, paginated movie list with filters (year range, minimum IMDb rating and Metascore, genre), search and sorting
- Public movie details, with certification, genres, stars and directors
- Public genre list with the number of movies in each genre
- Moderator endpoints to create, update and delete movies
- Moderator endpoints to manage genres, stars, directors and certifications
- Genres, stars, directors and certifications used by a movie cannot be deleted
- Command to load a sample catalog of 100 movies

## Tech Stack

- **Python 3.13**, **FastAPI**, **Pydantic v2**
- **PostgreSQL 18**, **SQLAlchemy 2.0** (async) with **asyncpg**, **Alembic** for migrations
- **JWT** authentication via **PyJWT**, **Argon2** password hashing via **pwdlib**
- **Celery** with **Redis** as the broker, and **Celery beat** for scheduled tasks
- **Docker** and **Docker Compose**, **Mailpit** for local email testing
- **Poetry** for dependency management
- **pytest** + **pytest-asyncio** + **pytest-cov** for testing
- **black**, **flake8**, **mypy** (strict) for code quality
- **GitHub Actions** for CI

## Quick Start (Docker)

Requires [Docker](https://docs.docker.com/get-docker/) with Docker Compose.

```bash
git clone https://github.com/omerlenko/online-cinema-api.git
cd online-cinema-api
cp .env.example .env
docker compose up --build
```

This starts PostgreSQL, Redis and Mailpit, waits until the database is healthy, applies database migrations, and starts
the API together with a Celery worker and Celery beat.

- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs (open by default in local development, see `DOCS_REQUIRE_AUTH`)
- Health check (includes database connectivity): http://localhost:8000/health
- Mailpit (catches all outgoing emails, e.g. activation links): http://localhost:8025

Useful commands:

```bash
docker compose down                          # stop all services (data is kept)
docker compose logs -f app                   # follow API logs
docker compose run --rm app alembic current  # run a one-off command in the app image
docker compose logs -f celery-worker celery-beat   # follow background task logs
```

### Trying it out

1. `POST /api/v1/accounts/register` with an email and password.
2. Open Mailpit (http://localhost:8025) and click the activation link.
3. `POST /api/v1/accounts/login` to receive an access token and a refresh token.
4. In the interactive docs, click **Authorize** and paste the access token to call protected endpoints such as
   `GET /api/v1/accounts/me`.
5. With a moderator or admin account, create a certification and a genre, then `POST /api/v1/movies` with their ids.
6. Or load the sample catalog (see [Loading sample movies](#loading-sample-movies)) and browse it without logging in,
   e.g. `GET /api/v1/movies?search=nolan&sort_by=imdb&order=desc`.

## Authentication

- **Access token:** a short-lived JWT (15 minutes by default), sent as `Authorization: Bearer <token>`.
- **Refresh token:** a long-lived JWT (7 days by default), stored in the database. `POST /accounts/refresh` exchanges it
  for a new access token.
- **Logout:** `POST /accounts/logout` deletes the refresh token. Each login creates its own refresh token, so logging
  out on one device does not affect others.

## User Groups and Permissions

Every account belongs to one group. New accounts start in `user`.

| Group       | Can do                                                                                   |
|-------------|------------------------------------------------------------------------------------------|
| `user`      | Use their own account                                                                    |
| `moderator` | Everything a user can do, plus manage the movie catalog                                  |
| `admin`     | Everything a moderator can do, plus list users, activate accounts and change user groups |

Admin endpoints:

- `GET /api/v1/accounts/users` lists users, using the shared [pagination](#pagination) format. Optional query
  parameters:
    - `is_active` (`true` or `false`) and `group` (`user`, `moderator` or `admin`) filter the list.
    - `search` matches part of the email address, ignoring letter case.
    - `sort_by` (`id` by default, or `email`) and `order` (`asc` by default, or `desc`) set the order.
- `POST /api/v1/accounts/users/{user_id}/activate` activates an account without the email link.
- `POST /api/v1/accounts/users/{user_id}/change-group` with `{"group_name": "moderator"}` moves a user to another group.
  Admins can change any user's group except their own, including demoting other admins.

The activate and change-group endpoints return the user's details, and repeating a request that changes nothing returns
200 OK.

### Creating the first admin

Admin rights can only be granted by an existing admin, so the first admin is created from the server:

```bash
docker compose exec app python -m src.accounts.create_admin admin@example.com
```

The command asks for the password twice, applies the same rules as registration, and creates an account that is already
active. When running the API locally, use `poetry run python -m src.accounts.create_admin admin@example.com` instead.

## Movie Management

| Resource                                 | Anyone                                                | Moderator or admin                                |
|------------------------------------------|-------------------------------------------------------|---------------------------------------------------|
| Movies                                   | `GET /api/v1/movies`, `GET /api/v1/movies/{movie_id}` | `POST /api/v1/movies`, `PATCH` and `DELETE` by id |
| Genres, stars, directors, certifications | `GET /api/v1/movies/genres` (and `/stars`, …)         | `POST`, and `PUT` and `DELETE` by id              |

- A new movie refers to its certification, genres, stars and directors by id. Unknown ids are rejected with 400, and
  the message lists every missing id.
- A movie is identified by its name, release year and duration: a second movie with the same three values is rejected
  with 409.
- `PATCH` changes only the fields that are sent. A list such as `genre_ids` replaces the current links, and an empty
  list removes them all.
- Genres, stars, directors and certifications are stored as typed; a name that differs only in letter case from an
  existing one is rejected.

### Browsing the catalog

`GET /api/v1/movies` returns a [page](#pagination) of movies. All query parameters are optional and can be combined:

| Parameter              | Effect                                                                                    |
|------------------------|-------------------------------------------------------------------------------------------|
| `year_from`, `year_to` | Release year range, both ends included                                                    |
| `min_imdb`             | Minimum IMDb rating (0–10)                                                                |
| `min_meta_score`       | Minimum Metascore (0–100); movies without one are left out                                |
| `genre_id`             | Only movies in this genre                                                                 |
| `search`               | Matches part of the name, description, or a genre, star or director name, ignoring case   |
| `sort_by`              | `id` (default), `name`, `year`, `time`, `imdb`, `votes`, `meta_score`, `gross` or `price` |
| `order`                | `asc` (default) or `desc`                                                                 |

- Movies without a Metascore or box office figure are listed last, in both sort orders. Movies with equal values are
  ordered by id, so paging through the results never skips or repeats a movie.
- List items are short: name, year, duration, ratings, votes, box office, price, certification and genres.
  `GET /api/v1/movies/{movie_id}` adds the description, stars and directors.
- `GET /api/v1/movies/genres` includes `movie_count`, the number of movies in each genre.

### Loading sample movies

To try the catalog without entering movies by hand, load the sample data:

```bash
docker compose exec app python -m src.movies.seed
```

When running the API locally, use `poetry run python -m src.movies.seed` instead.

- The whole file is validated with the same rules as `POST /api/v1/movies` before anything is written, and all movies
  are saved in one transaction, so a failed run changes nothing.
- The command can be run again safely: movies that already exist (same name, release year and duration) are skipped,
  and existing genres, stars, directors and certifications are reused.
- The sample catalog contains 100 well-known movies with original descriptions written for this project. Ratings,
  votes and box office figures are approximate. The data is not affiliated with or taken from IMDb.

## Pagination

Both lists (`GET /api/v1/movies` and the admin user list) take `page` (default 1) and `page_size` (default 20, at most
100), and return:

```json
{
  "items": [],
  "total": 42,
  "page": 2,
  "page_size": 20,
  "previous_page": "http://localhost:8000/api/v1/movies?genre_id=3&page=1&page_size=20",
  "next_page": "http://localhost:8000/api/v1/movies?genre_id=3&page=3&page_size=20"
}
```

- `total` counts every match, not just the current page.
- `previous_page` and `next_page` are full links that keep the filters, search and sorting of the current request, or
  `null` on the first or last page.
- A page past the end returns an empty `items` list, not an error.

## Background Tasks

Celery beat schedules a cleanup task that a Celery worker runs every 60 minutes
(`EXPIRED_TOKEN_CLEANUP_INTERVAL_MINUTES`).
It deletes expired activation, refresh and password reset tokens, and logs how many rows it removed.

Run it by hand, without waiting for the schedule:

```bash
docker compose exec celery-worker celery -A src.celery_app call src.accounts.tasks.purge_expired_tokens
```

- Redis is used only as the Celery broker. Task results are not stored, and Redis is not published outside the Compose
  network.
- The worker and beat use the same image as the API, but skip the migration step.
- Tasks use their own database engine without a connection pool, because every task run starts a new event loop.

## API Documentation Access

Swagger UI (`/docs`), ReDoc (`/redoc`) and the OpenAPI schema (`/openapi.json`) can be restricted to registered users.

- With `DOCS_REQUIRE_AUTH=True` (the default when the variable is not set), the browser asks for an email and password
  via HTTP Basic authentication. Any active account is accepted.
- `.env.example` sets `DOCS_REQUIRE_AUTH=False`, so the docs are open in local development.

## Security Decisions and Known Limitations

- **Passwords** are hashed with Argon2 and never stored or returned in plain text.
- **Activation uses GET**, because the link is opened from an email and there is no frontend. Activation tokens are kept
  until they expire, so opening the link twice is harmless.
- **Resend activation** returns the same response for every email, and **login** returns the same 401 for an unknown
  email and a wrong password, so neither reveals whether an email is registered. Login response time is not equalized
  between the two cases.
- **Registration** returns 409 for an email that is already taken, which does reveal that it is registered. This is
  accepted for usability.
- **Access tokens are stateless** and cannot be revoked before they expire, which is why their lifetime is short. After
  logout, an access token stays valid until it expires.
- **Refresh tokens** carry a `type` claim, so they cannot be used as access tokens, and a unique `jti`. They are valid
  only while their row exists in the database.
- **Refresh tokens are stored unhashed.** A database leak would expose usable tokens until they expire. Hashing them is
  a possible improvement.
- **No refresh token rotation or reuse detection.** A stolen refresh token stays valid until it expires or the user logs
  out.
- **Inactive accounts** cannot log in, refresh, or use existing access tokens.
- **API documentation** is protected with HTTP Basic authentication when `DOCS_REQUIRE_AUTH` is enabled. Basic
  credentials are sent with every request, so this relies on HTTPS in production.
- **Password reset tokens** are stored hashed (SHA-256), work only once, and expire after 15 minutes. A new request
  replaces the previous token. Activation and refresh tokens are stored unhashed, because their value to an attacker is
  lower.
- **Forgot password** returns the same response for every email, and only sends a token to registered, active accounts.
- **Changing a password** logs out the user's other sessions; **resetting** it logs out all of them. Access tokens
  already issued stay valid until they expire.
- **Reset tokens are sent in the request body**, never in a URL, so they do not end up in server logs. With no frontend,
  the email contains the token itself rather than a link.
- **Expired tokens** are deleted by a scheduled task, so they do not pile up in the database. A link opened after the
  cleanup gets the same "invalid or expired" response as before.
- **Groups are read from the database on every request**, not stored in the token. A promotion or demotion takes
  effect on the user's next request, even with an access token issued earlier.
- **Admins cannot change their own group**, so there is always at least one admin. One admin can, however, remove the
  rights of all the others.
- **The first admin is created on the server**, never through the API. The password is typed at a hidden prompt rather
  than passed as an argument, so it does not end up in shell history.
- **Catalog data in use cannot be deleted.** Deleting a genre, star, director or certification that a movie still uses
  is refused with 409. Deleting a movie removes its links but keeps the genres, stars and directors.
- **Duplicate names are caught only by letter case.** "Drama" and "drama" are the same genre, but different spellings
  of one thing, such as "Sci-Fi" and "Science Fiction", are not detected. Moderators keep these lists clean.
- **In `PATCH`, `null` means "no change"**, so the optional `meta_score` and `gross` cannot be cleared back to empty.
- **The genre filter takes one genre at a time.** Movies in several genres can be found by any one of them.
- **Search uses a simple case-insensitive substring match** (`ILIKE`), without a full-text index. That is fast enough
  for a catalog of this size, but would need a search index for a much larger one.

## Configuration

All settings are read from environment variables, loaded from `.env` for local development.

| Variable                                 | Description                                     | Local default           |
|------------------------------------------|-------------------------------------------------|-------------------------|
| `POSTGRES_DB`                            | Database name                                   | `cinema_db`             |
| `POSTGRES_USER`                          | Database user                                   | `admin`                 |
| `POSTGRES_PASSWORD`                      | Database password                               | —                       |
| `POSTGRES_HOST`                          | Database host                                   | `localhost`             |
| `POSTGRES_PORT`                          | Database port                                   | `5432`                  |
| `SMTP_HOST`                              | SMTP server host                                | `localhost`             |
| `SMTP_PORT`                              | SMTP server port                                | `1025`                  |
| `SMTP_USER`                              | SMTP username (optional)                        | —                       |
| `SMTP_PASSWORD`                          | SMTP password (optional)                        | —                       |
| `SMTP_USE_TLS`                           | Use STARTTLS when connecting to the SMTP server | `False`                 |
| `EMAIL_SENDER_ADDRESS`                   | "From" address of outgoing emails               | `noreply@example.com`   |
| `BASE_URL`                               | Public base URL used in links sent by email     | `http://127.0.0.1:8000` |
| `API_VERSION_PREFIX`                     | Prefix for all API routes                       | `/api/v1`               |
| `ACTIVATION_TOKEN_LIFETIME_DAYS`         | Lifetime of account activation links            | `1`                     |
| `DOCS_REQUIRE_AUTH`                      | Require login to view the API documentation     | `False`                 |
| `JWT_SECRET_KEY`                         | Secret used to sign JWTs (required, 32+ chars)  | —                       |
| `JWT_ALGORITHM`                          | JWT signing algorithm                           | `HS256`                 |
| `JWT_ACCESS_TOKEN_LIFETIME_MINUTES`      | Access token lifetime                           | `15`                    |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS`        | Refresh token lifetime                          | `7`                     |
| `PASSWORD_RESET_TOKEN_LIFETIME_MINUTES`  | Lifetime of password reset tokens               | `15`                    |
| `EXPIRED_TOKEN_CLEANUP_INTERVAL_MINUTES` | How often expired tokens are deleted            | `60`                    |
| `REDIS_HOST`                             | Redis host (Celery broker)                      | `localhost`             |
| `REDIS_PORT`                             | Redis port                                      | `6379`                  |

When running in Docker Compose, the API container overrides `POSTGRES_HOST` to `db` and `SMTP_HOST` to `mailpit`. The
Celery containers override `REDIS_HOST` to `redis`, and the worker also overrides `POSTGRES_HOST` to `db`.

Generate a real `JWT_SECRET_KEY` with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## Local Development

Runs the API directly on your machine, with only the infrastructure in Docker.

### Prerequisites

- Python 3.13
- [Poetry](https://python-poetry.org/) 2.x
- Docker with Docker Compose

### Setup

```bash
poetry install
cp .env.example .env
docker compose up -d db mailpit
poetry run alembic upgrade head
poetry run uvicorn src.main:app --reload
```

Stop the API container first (`docker compose stop app`) if the full stack is running, since both use port 8000.
The Celery worker and beat run only in Docker Compose. Running the API locally and running the tests need neither Celery
nor Redis.

### Migrations

```bash
poetry run alembic revision --autogenerate -m "describe the change"   # create a migration
poetry run alembic upgrade head                                       # apply migrations
poetry run alembic check                                              # verify models match migrations
```

### Running tests

Tests require PostgreSQL to be running (`docker compose up -d db`). A separate test database (`<POSTGRES_DB>_test`) is
created automatically, and every test runs in a transaction that is rolled back afterward. Emails are captured by a
fake sender, so no SMTP server is needed.

```bash
poetry run pytest          # run all tests
poetry run pytest --cov    # with coverage report
```

### Code quality

```bash
poetry run black --check .
poetry run flake8
poetry run mypy .
```

## Project Structure

```
src/
├── accounts/       # registration, authentication, user groups, admin command, token cleanup task
├── core/           # settings, security (hashing, JWT), email sending, pagination, shared schemas
├── database/       # engine, sessions, declarative base
├── movies/         # movies, genres, stars, directors, certifications: models, schemas, endpoints, sample data command
├── celery_app.py   # Celery app and beat schedule
└── main.py         # FastAPI app, health check, protected docs
migrations/     # Alembic database migrations
commands/       # container entrypoint scripts
tests/
├── unit/         # pure logic, no database
├── integration/  # endpoints against a real test database
└── e2e/          # full user flows across several endpoints
```
