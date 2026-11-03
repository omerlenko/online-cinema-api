# Online Cinema API

[![CI](https://github.com/omerlenko/online-cinema-api/actions/workflows/ci-pipeline.yml/badge.svg?branch=main)](https://github.com/omerlenko/online-cinema-api/actions/workflows/ci-pipeline.yml)

Backend API for an online cinema platform where users can browse, purchase, and watch movies. Built with FastAPI and
async SQLAlchemy.

> 🚧 In active development.

Live API: http://18.199.230.210/api/v1/movies (see [Deployment](#deployment))

## Features

**Accounts**

- Registration with email activation, login with JWT access and refresh tokens, and logout
- Password change, and password reset with an emailed single-use token
- User groups (user, moderator, admin) with permission checks
- Admin endpoints to list users, activate accounts and change groups, and a command to create the first admin
- Scheduled cleanup of expired tokens with Celery

**Movies**

- Public, paginated movie list with filters, search and sorting, and movie details
- Moderator endpoints to manage movies, genres, stars, directors and certifications
- Command to load a sample catalog of 100 movies

**Cart**

- One cart per user: add and remove movies, clear the cart, and list it
- Moderator view of any user's cart, and a warning before deleting a movie that is in carts

## Tech Stack

- **Python 3.13**, **FastAPI**, **Pydantic v2**
- **PostgreSQL 18**, **SQLAlchemy 2.0** (async) with **asyncpg**, **Alembic** for migrations
- **JWT** authentication via **PyJWT**, **Argon2** password hashing via **pwdlib**
- **Celery** with **Redis** as the broker, and **Celery beat** for scheduled tasks
- **Docker** and **Docker Compose**, **Mailpit** for email testing
- **Poetry** for dependency management
- **pytest** + **pytest-asyncio** + **pytest-cov** for testing
- **black**, **flake8**, **mypy** (strict) for code quality
- **GitHub Actions** for CI and automatic deployment to **AWS EC2**, with images stored in **GitHub Container Registry**

## Quick Start (Docker)

Requires [Docker](https://docs.docker.com/get-docker/) with Docker Compose.

```bash
git clone https://github.com/omerlenko/online-cinema-api.git
cd online-cinema-api
cp .env.example .env
docker compose up --build
```

This starts PostgreSQL, Redis and Mailpit, applies database migrations, and starts the API with a Celery worker and
Celery beat.

- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs (every endpoint, parameter and error response is documented there)
- Health check (includes database connectivity): http://localhost:8000/health
- Mailpit (catches all outgoing emails, e.g. activation links): http://localhost:8025

```bash
docker compose down                                # stop all services (data is kept)
docker compose logs -f app                         # follow API logs
docker compose logs -f celery-worker celery-beat   # follow background task logs
docker compose run --rm app alembic current        # run a one-off command in the app image
```

### Trying it out

1. `POST /api/v1/accounts/register` with an email and password.
2. Open Mailpit (http://localhost:8025) and click the activation link.
3. `POST /api/v1/accounts/login` to receive an access token and a refresh token.
4. In the interactive docs, click **Authorize** and paste the access token to call protected endpoints such as
   `GET /api/v1/accounts/me`.
5. Load the sample catalog (see [Loading sample movies](#loading-sample-movies)) and browse it without logging in,
   e.g. `GET /api/v1/movies?search=nolan&sort_by=imdb&order=desc`.
6. Logged in, add a movie to your cart with `POST /api/v1/cart/items` and `{"movie_id": 1}`, then view it with
   `GET /api/v1/cart`.

## Accounts and Security

- **Access tokens** are short-lived JWTs (15 minutes by default), sent as `Authorization: Bearer <token>`. They are
  stateless, so they cannot be revoked and stay valid until they expire, even after logout.
- **Refresh tokens** are long-lived JWTs (7 days by default), valid only while their row exists in the database.
  `POST /accounts/refresh` exchanges one for a new access token, and `POST /accounts/logout` deletes it. Each login
  creates its own refresh token, so logging out on one device does not affect others. A `type` claim stops them from
  being used as access tokens.
- **Passwords** are hashed with Argon2. Changing a password logs out the user's other sessions, and resetting it logs
  out all of them.
- **Password reset tokens** are stored hashed (SHA-256), work once, expire after 15 minutes, and are sent in the request
  body rather than a URL, so they do not end up in server logs. With no frontend, the email contains the token itself.
- **Activation uses GET**, because the link is opened from an email. Opening it twice is harmless.
- **No email enumeration** on resend activation, forgot password and login: they respond the same way whether or not
  the email is registered. Registration does return 409 for a taken email, which is accepted for usability.
- **Inactive accounts** cannot log in, refresh, or use existing access tokens.

### User groups

Every account belongs to one group. New accounts start in `user`. Groups are read from the database on every request,
so a promotion or demotion takes effect immediately, even with an access token issued earlier.

| Group       | Can do                                                                                   |
|-------------|------------------------------------------------------------------------------------------|
| `user`      | Use their own account and cart                                                           |
| `moderator` | Everything a user can do, plus manage the movie catalog and view any user's cart         |
| `admin`     | Everything a moderator can do, plus list users, activate accounts and change user groups |

- `GET /api/v1/accounts/users` lists users ([paginated](#pagination)), with filters by status and group, search by
  email, and sorting.
- `POST /api/v1/accounts/users/{user_id}/activate` activates an account without the email link.
- `POST /api/v1/accounts/users/{user_id}/change-group` moves a user to another group. Admins cannot change their own
  group, so there is always at least one admin.

### Creating the first admin

Admin rights can only be granted by an existing admin, so the first admin is created on the server:

```bash
docker compose exec app python -m src.accounts.create_admin admin@example.com
```

The command asks for the password at a hidden prompt, so it does not end up in shell history, and applies the same
rules as registration. Locally, use `poetry run python -m src.accounts.create_admin admin@example.com`.

## Movies

| Resource                                 | Anyone                                                | Moderator or admin                                |
|------------------------------------------|-------------------------------------------------------|---------------------------------------------------|
| Movies                                   | `GET /api/v1/movies`, `GET /api/v1/movies/{movie_id}` | `POST /api/v1/movies`, `PATCH` and `DELETE` by id |
| Genres, stars, directors, certifications | `GET /api/v1/movies/genres` (and `/stars`, …)         | `POST`, and `PUT` and `DELETE` by id              |

- A movie is identified by its name, release year and duration; a duplicate is rejected with 409.
- A movie refers to its certification, genres, stars and directors by id. Unknown ids are rejected with 400, and the
  message lists all of them.
- `PATCH` changes only the fields that are sent. A list such as `genre_ids` replaces the current links.
- Genre, star, director and certification names are unique regardless of letter case. Ones still used by a movie
  cannot be deleted (409).
- Deleting a movie that is in at least one cart is refused with 409, and the message says how many carts contain it.
  `?force=true` deletes it anyway and removes it from those carts.

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

Movies without a Metascore or box office figure are listed last in both orders. Ties are ordered by id, so paging
never skips or repeats a movie.

### Loading sample movies

```bash
docker compose exec app python -m src.movies.seed
```

Locally, use `poetry run python -m src.movies.seed`. The file is validated with the same rules as `POST /api/v1/movies`
and saved in one transaction, so a failed run changes nothing. Running it again skips movies that already exist.

The 100 sample movies have original descriptions written for this project. Ratings, votes and box office figures are
approximate, and the data is not affiliated with or taken from IMDb.

## Cart

| Endpoint                               | Effect                                                      |
|----------------------------------------|-------------------------------------------------------------|
| `GET /api/v1/cart`                     | Lists the movies in your cart, in the order they were added |
| `POST /api/v1/cart/items`              | Adds a movie, with `{"movie_id": 1}`                        |
| `DELETE /api/v1/cart/items/{movie_id}` | Removes a movie                                             |
| `DELETE /api/v1/cart`                  | Removes every movie                                         |
| `GET /api/v1/cart/users/{user_id}`     | Moderator or admin: lists any user's cart                   |

- Every cart endpoint requires login. The 401 without a token tells a client to ask the user to sign up or log in.
- The cart is created on the first add. Listing, removing and clearing never create one.
- Items are identified by the movie id, and each item shows the movie's name, year, price and genres, and when it was
  added.
- Two first adds at the same moment share one cart (`INSERT ... ON CONFLICT DO NOTHING`), and the same movie added
  twice at once gets 409 from a unique constraint.
- The cart is not paginated, because it holds only the few movies a user is about to buy.

## Pagination

Movie and user lists take `page` (default 1) and `page_size` (default 20, at most 100), and return:

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

`previous_page` and `next_page` keep the filters, search and sorting of the current request, and are `null` on the
first or last page. A page past the end returns an empty `items` list.

## Background Tasks

Celery beat schedules a task, run by a Celery worker every 60 minutes (`EXPIRED_TOKEN_CLEANUP_INTERVAL_MINUTES`), that
deletes expired activation, refresh and password reset tokens. To run it now:

```bash
docker compose exec celery-worker celery -A src.celery_app call src.accounts.tasks.purge_expired_tokens
```

Redis is used only as the broker and is not reachable from outside the Compose network. Tasks use their own database
engine without a connection pool, because every task run starts a new event loop.

## API Documentation Access

With `DOCS_REQUIRE_AUTH=True` (the default when the variable is not set), Swagger UI (`/docs`), ReDoc (`/redoc`) and
`/openapi.json` ask for the email and password of any active account, via HTTP Basic authentication. `.env.example`
sets it to `False`, so the docs are open in local development.

## Known Limitations

**Deployment**

- **No HTTPS.** The server is reached by IP address over plain HTTP, so passwords, tokens and documentation credentials
  are not encrypted in transit. A domain name and a reverse proxy such as Caddy would fix this.
- **Production email goes to Mailpit**, not to real inboxes, so an admin activates new accounts with the activate
  endpoint. A real provider needs only the `SMTP_*` settings.
- **Emails are sent from the API process**, so an email being sent during a restart, such as a deploy, can be lost.
  Moving email to Celery would add retries.
- **SSH is open to the internet**, because GitHub's runners have no fixed IP address. Login works with keys only.
- **Deploys cause a few seconds of downtime**, and a failed deploy is not rolled back automatically.

**Accounts**

- **Refresh tokens are stored unhashed**, and there is no rotation or reuse detection. A stolen refresh token stays
  valid until it expires or the user logs out.
- **Login response time** is not equalized between an unknown email and a wrong password.
- **One admin can remove the rights of all the others.**

**Movies and cart**

- **Duplicate names are caught only by letter case.** "Sci-Fi" and "Science Fiction" are not detected.
- **In `PATCH`, `null` means "no change"**, so `meta_score` and `gross` cannot be cleared once set.
- **The genre filter takes one genre at a time.**
- **Search is a substring match** (`ILIKE`) without a full-text index: fine for this catalog size, not for a much
  larger one.
- **Movies already purchased can still be added to the cart.** This check needs orders, which are not built yet.
- **Users are not notified** when a moderator force-deletes a movie that is in their cart.

## Configuration

All settings are read from environment variables, loaded from `.env` both locally and on the server.

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

In Docker Compose, the containers override the hosts to point at the other services (`db`, `mailpit`, `redis`).

Generate a real `JWT_SECRET_KEY` with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## Local Development

Runs the API on your machine, with only the infrastructure in Docker. Requires Python 3.13,
[Poetry](https://python-poetry.org/) 2.x and Docker.

```bash
poetry install
cp .env.example .env
docker compose up -d db mailpit
poetry run alembic upgrade head
poetry run uvicorn src.main:app --reload
```

Stop the API container first (`docker compose stop app`) if the full stack is running, since both use port 8000.
Celery runs only in Docker Compose; the local API and the tests do not need it.

```bash
poetry run alembic revision --autogenerate -m "describe the change"   # create a migration
poetry run alembic check                                              # verify models match migrations
poetry run pytest --cov                                               # tests with coverage
poetry run black --check .                                            # formatting
poetry run flake8                                                     # linting
poetry run mypy .                                                     # type checks
```

Tests need PostgreSQL running (`docker compose up -d db`). They create a separate `<POSTGRES_DB>_test` database, roll
back every test's transaction, and capture emails with a fake sender.

## Deployment

Every merge into `main` is deployed automatically to an AWS EC2 server by `.github/workflows/ci-pipeline.yml`:

1. **Test:** formatting, linting, type checks, the migration check and the test suite.
2. **Build:** the Docker image is built. After a merge, it is pushed to GitHub Container Registry, tagged with the
   commit SHA and `latest`.
3. **Deploy:** GitHub Actions connects to the server over SSH, copies `docker-compose.prod.yaml`, pulls the image for
   that commit and restarts the services. Migrations run when the API container starts.
4. **Verify:** `/health` is called from outside the server, and the job fails if the API or the database does not
   respond.

Each stage runs only if the previous one passed. Pull requests run the first two stages, without pushing the image.

### Production setup

- The API, worker and beat run the same image from the registry, so nothing is built on the server.
- Only the API is public, on port 80. PostgreSQL and Redis have no published ports, and Mailpit's web UI listens only
  on `127.0.0.1`, because it shows every activation and password reset email.
- All services restart automatically after a crash or a reboot.
- Production settings live in a `.env` file on the server, readable only by its owner, never in the image or the
  repository. GitHub Secrets hold only what the pipeline needs to reach the server.

To read emails on the server, open an SSH tunnel and visit http://localhost:8025:

```bash
ssh -L 8025:localhost:8025 ubuntu@<server-ip>
```

To roll back, run this on the server, from the folder with the Compose file:

```bash
IMAGE_TAG=<commit-sha> docker compose -f docker-compose.prod.yaml up -d
```

This changes the code only. Migrations are not reversed, so the older version must still work with the current schema.

## Project Structure

```
src/
├── accounts/       # registration, authentication, user groups, admin command, token cleanup task
├── cart/           # shopping cart
├── core/           # settings, security (hashing, JWT), email sending, pagination, shared schemas
├── database/       # engine, sessions, declarative base
├── movies/         # movie catalog and sample data command
├── celery_app.py   # Celery app and beat schedule
└── main.py         # FastAPI app, health check, protected docs
migrations/         # Alembic database migrations
commands/           # container entrypoint script
.github/            # CI and deployment pipeline
tests/
├── unit/           # pure logic, no database
├── integration/    # endpoints against a real test database
└── e2e/            # full user flows across several endpoints
```
