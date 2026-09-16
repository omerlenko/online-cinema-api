# Online Cinema API

[![CI](https://github.com/omerlenko/online-cinema-api/actions/workflows/ci-pipeline.yml/badge.svg?branch=main)](https://github.com/omerlenko/online-cinema-api/actions/workflows/ci-pipeline.yml)

Backend API for an online cinema platform where users can browse, purchase, and watch movies. Built with FastAPI and
async SQLAlchemy.

> 🚧 In active development.

## Tech Stack

- **Python 3.13**, **FastAPI**, **Pydantic v2**
- **PostgreSQL 18**, **SQLAlchemy 2.0** (async) with **asyncpg**, **Alembic** for migrations
- **Docker Compose** for local services
- **Poetry** for dependency management
- **pytest** + **pytest-asyncio** + **pytest-cov** for testing
- **black**, **flake8**, **mypy** (strict) for code quality
- **GitHub Actions** for CI

## Getting Started

### Prerequisites

- Python 3.13
- [Poetry](https://python-poetry.org/) 2.x
- [Docker](https://docs.docker.com/get-docker/) with Docker Compose

### Installation

```bash
git clone https://github.com/omerlenko/online-cinema-api.git
cd online-cinema-api
poetry install
cp .env.example .env
```

### Configuration

All settings are read from environment variables, loaded from `.env` for local development.

| Variable            | Description       | Local default |
|---------------------|-------------------|---------------|
| `POSTGRES_DB`       | Database name     | `cinema_db`   |
| `POSTGRES_USER`     | Database user     | `admin`       |
| `POSTGRES_PASSWORD` | Database password | —             |
| `POSTGRES_HOST`     | Database host     | `localhost`   |
| `POSTGRES_PORT`     | Database port     | `5432`        |

### Database

Start PostgreSQL and apply migrations:

```bash
docker compose up -d db
poetry run alembic upgrade head
```

### Running the app

```bash
poetry run uvicorn src.main:app --reload
```

- API: http://127.0.0.1:8000
- Interactive docs: http://127.0.0.1:8000/docs
- Health check (includes database connectivity): http://127.0.0.1:8000/health

## Development

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
tests/          # unit, integration, and end-to-end tests
```
