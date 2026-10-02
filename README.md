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

## Tech Stack

- **Python 3.13**, **FastAPI**, **Pydantic v2**
- **PostgreSQL 18**, **SQLAlchemy 2.0** (async) with **asyncpg**, **Alembic** for migrations
- **Argon2** password hashing via **pwdlib**
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

## Configuration

All settings are read from environment variables, loaded from `.env` for local development.

| Variable               | Description                                     | Local default           |
|------------------------|-------------------------------------------------|-------------------------|
| `POSTGRES_DB`          | Database name                                   | `cinema_db`             |
| `POSTGRES_USER`        | Database user                                   | `admin`                 |
| `POSTGRES_PASSWORD`    | Database password                               | —                       |
| `POSTGRES_HOST`        | Database host                                   | `localhost`             |
| `POSTGRES_PORT`        | Database port                                   | `5432`                  |
| `SMTP_HOST`            | SMTP server host                                | `localhost`             |
| `SMTP_PORT`            | SMTP server port                                | `1025`                  |
| `SMTP_USER`            | SMTP username (optional)                        | —                       |
| `SMTP_PASSWORD`        | SMTP password (optional)                        | —                       |
| `SMTP_USE_TLS`         | Use STARTTLS when connecting to the SMTP server | `False`                 |
| `EMAIL_SENDER_ADDRESS` | "From" address of outgoing emails               | `noreply@example.com`   |
| `BASE_URL`             | Public base URL used in links sent by email     | `http://127.0.0.1:8000` |
| `API_VERSION_PREFIX`   | Prefix for all API routes                       | `/api/v1`               |

When running in Docker Compose, the API container overrides `POSTGRES_HOST` to `db` and `SMTP_HOST` to `mailpit`.

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
├── accounts/   # registration and activation: models, schemas, endpoints
├── core/       # settings, security, email sending, shared schemas
└── database/   # engine, sessions, declarative base
migrations/     # Alembic database migrations
commands/       # container entrypoint scripts
tests/
├── unit/         # pure logic, no database
└── integration/  # endpoints against a real test database
```
