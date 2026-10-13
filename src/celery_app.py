from datetime import timedelta

from celery import Celery

from src.core.config import get_settings

settings = get_settings()


app = Celery(
    "online_cinema",
    broker=settings.REDIS_URL,
    include=["src.accounts.tasks"],
)


app.conf.update(
    task_ignore_result=True,
    beat_schedule={
        "purge_expired_tokens": {
            "task": "src.accounts.tasks.purge_expired_tokens",
            "schedule": timedelta(
                minutes=settings.EXPIRED_TOKEN_CLEANUP_INTERVAL_MINUTES
            ),
        },
    },
)
