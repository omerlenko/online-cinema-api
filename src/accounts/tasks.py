import asyncio

from src.database.session import TaskSession
from src.accounts.crud import delete_expired_tokens
from src.celery_app import app


async def _purge_expired_tokens() -> int:
    async with TaskSession() as session:
        deleted_count = await delete_expired_tokens(db=session)
        await session.commit()
    return deleted_count


@app.task
def purge_expired_tokens() -> int:
    """Delete expired activation, refresh and password reset tokens."""

    return asyncio.run(_purge_expired_tokens())
