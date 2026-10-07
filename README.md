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

## Tech Stack

- **Python 3.13**, **FastAPI**, **Pydantic v2**
- **PostgreSQL 18**, **SQLAlchemy 2.0** (async) with **asyncpg**, **Alembic** for migrations
- **JWT** authentication via **PyJWT**, **Argon2** password hashing via **pwdlib**
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

This starts PostgreSQL and Mailpit, waits until the database is healthy, applies database migrations, and starts the
API.

- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- Health check (includes database connectivity): http://localhost:8000/health
- Mailpit (catches all outgoing emails, e.g. activation links): http://localhost:8025

Useful commands:

```bash
docker compose down                          # stop all services (data is kept)
docker compose logs -f app                   # follow API logs
docker compose run --rm app alembic current  # run a one-off command in the app image
```

### Trying it out

1. `POST /api/v1/accounts/register` with an email and password.
2. Open Mailpit (http://localhost:8025) and click the activation link.
3. `POST /api/v1/accounts/login` to receive an access token and a refresh token.
4. In the interactive docs, click **Authorize** and paste the access token to call protected endpoints such as
   `GET /api/v1/accounts/me`.

## Authentication

- **Access token:** a short-lived JWT (15 minutes by default), sent as `Authorization: Bearer <token>`.
- **Refresh token:** a long-lived JWT (7 days by default), stored in the database. `POST /accounts/refresh` exchanges it
  for a new access token.
- **Logout:** `POST /accounts/logout` deletes the refresh token. Each login creates its own refresh token, so logging
  out on one device does not affect others.

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

## Configuration

All settings are read from environment variables, loaded from `.env` for local development.

| Variable                            | Description                                     | Local default           |
|-------------------------------------|-------------------------------------------------|-------------------------|
| `POSTGRES_DB`                       | Database name                                   | `cinema_db`             |
| `POSTGRES_USER`                     | Database user                                   | `admin`                 |
| `POSTGRES_PASSWORD`                 | Database password                               | —                       |
| `POSTGRES_HOST`                     | Database host                                   | `localhost`             |
| `POSTGRES_PORT`                     | Database port                                   | `5432`                  |
| `SMTP_HOST`                         | SMTP server host                                | `localhost`             |
| `SMTP_PORT`                         | SMTP server port                                | `1025`                  |
| `SMTP_USER`                         | SMTP username (optional)                        | —                       |
| `SMTP_PASSWORD`                     | SMTP password (optional)                        | —                       |
| `SMTP_USE_TLS`                      | Use STARTTLS when connecting to the SMTP server | `False`                 |
| `EMAIL_SENDER_ADDRESS`              | "From" address of outgoing emails               | `noreply@example.com`   |
| `BASE_URL`                          | Public base URL used in links sent by email     | `http://127.0.0.1:8000` |
| `API_VERSION_PREFIX`                | Prefix for all API routes                       | `/api/v1`               |
| `ACTIVATION_TOKEN_LIFETIME_DAYS`    | Lifetime of account activation links            | `1`                     |
| `JWT_SECRET_KEY`                    | Secret used to sign JWTs (required, 32+ chars)  | —                       |
| `JWT_ALGORITHM`                     | JWT signing algorithm                           | `HS256`                 |
| `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` | Access token lifetime                           | `15`                    |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS`   | Refresh token lifetime                          | `7`                     |

When running in Docker Compose, the API container overrides `POSTGRES_HOST` to `db` and `SMTP_HOST` to `mailpit`.

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

### Migrations

```bash
poetry run alembic revision --autogenerate -m "describe the change"   # create a migration
poetry run alembic upgrade head                                       # apply migrations
poetry run alembic check                                              # verify models match migrations
```

### Running tests

Tests require PostgreSQL to be running (`docker compose up -d db`). A separate test database (`<POSTGRES_DB>_test`) is
created automatically, and every test runs in a transaction that is rolled back afterwards. Emails are captured by a
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
├── accounts/   # registration, activation, authentication: models, schemas, endpoints
├── core/       # settings, security (hashing, JWT), email sending, shared schemas
└── database/   # engine, sessions, declarative base
migrations/     # Alembic database migrations
commands/       # container entrypoint scripts
tests/
├── unit/         # pure logic, no database
├── integration/  # endpoints against a real test database
└── e2e/          # full user flows across several endpoints
```
