# Online Cinema API

[![CI Status](https://github.com/omerlenko/online-cinema-api/actions/workflows/ci-pipeline.yml/badge.svg)]
([![CI](https://github.com/omerlenko/online-cinema-api/actions/workflows/ci-pipeline.yml/badge.svg?branch=main)](https://github.com/omerlenko/online-cinema-api/actions/workflows/ci-pipeline.yml))

Backend API for an online cinema platform where users can browse, purchase, and watch movies. Built with FastAPI and
async SQLAlchemy.

> 🚧 In active development.

## Tech Stack

- **Python 3.13**, **FastAPI**, **Pydantic v2**
- **SQLAlchemy 2.0** (async) with **asyncpg**, **Alembic** for migrations
- **Poetry** for dependency management
- **pytest** + **pytest-asyncio** + **pytest-cov** for testing
- **black**, **flake8**, **mypy** (strict) for code quality

## Getting Started

### Prerequisites

- Python 3.13
- [Poetry](https://python-poetry.org/) 2.x

### Installation

```bash
git clone https://github.com/omerlenko/online-cinema-api.git
cd online-cinema-api
poetry install
```

### Running the app

```bash
poetry run uvicorn src.main:app --reload
```

- API: http://127.0.0.1:8000
- Interactive docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

## Development

### Running tests

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
src/        # application code
tests/      # unit, integration, and end-to-end tests
```
