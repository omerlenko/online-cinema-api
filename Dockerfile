FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

COPY ./poetry.lock .
COPY ./pyproject.toml .

RUN pip install "poetry==2.4.3" &&\
    poetry install --only main --no-interaction --no-ansi

COPY ./src ./src
COPY ./migrations ./migrations
COPY ./alembic.ini .
COPY ./commands ./commands

RUN groupadd -r appgroup && useradd -r -g appgroup -s /bin/false appuser
RUN chmod 755 ./commands/*.sh

USER appuser

EXPOSE 8000
ENTRYPOINT ["/app/commands/entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
