# Online Cinema API

[![CI](https://github.com/omerlenko/online-cinema-api/actions/workflows/ci-pipeline.yml/badge.svg?branch=main)](https://github.com/omerlenko/online-cinema-api/actions/workflows/ci-pipeline.yml)

Backend API for an online cinema platform where users can browse, purchase, and watch movies. Built with FastAPI and
async SQLAlchemy.

> 🚧 In active development.

## Tech Stack

- **Python 3.13**, **FastAPI**, **Pydantic v2**
- **PostgreSQL 18**, **SQLAlchemy 2.0** (async) with **asyncpg**, **Alembic** for migrations
- **Docker** and **Docker Compose**
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

This starts PostgreSQL, waits until it is healthy, applies database migrations, and starts the API.

- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- Health check (includes database connectivity): http://localhost:8000/health

Useful commands:

```bash
docker compose down                          # stop all services (data is kept)
docker compose logs -f app                   # follow API logs
docker compose run --rm app alembic current  # run a one-off command in the app image
```

## Configuration

All settings are read from environment variables, loaded from `.env` for local development.

| Variable            | Description       | Local default |
|---------------------|-------------------|---------------|
| `POSTGRES_DB`       | Database name     | `cinema_db`   |
| `POSTGRES_USER`     | Database user     | `admin`       |
| `POSTGRES_PASSWORD` | Database password | —             |
| `POSTGRES_HOST`     | Database host     | `localhost`   |
| `POSTGRES_PORT`     | Database port     | `5432`        |

When running in Docker Compose, `POSTGRES_HOST` is overridden to `db` for the API container.

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
docker compose up -d db
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
created automatically, and every test runs in a transaction that is rolled back afterwards.

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
src/            # application code
migrations/     # Alembic database migrations
commands/       # container entrypoint scripts
tests/          # unit, integration, and end-to-end tests
```
