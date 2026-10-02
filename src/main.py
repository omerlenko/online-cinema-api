import logging

from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from src.accounts.router import router as accounts_router
from src.core.config import get_settings
from src.database.session import DbDep
from src.core.schemas import HealthResponseSchema, ErrorResponseSchema

app = FastAPI()
settings = get_settings()
api_version_prefix = settings.API_VERSION_PREFIX
app.include_router(
    accounts_router, prefix=f"{api_version_prefix}/accounts", tags=["accounts"]
)

logger = logging.getLogger(__name__)


@app.get(
    "/health",
    summary="Check health",
    responses={
        503: {"model": ErrorResponseSchema, "description": "Database unavailable"}
    },
)
async def health(db: DbDep) -> HealthResponseSchema:
    """
    Check if app and database are running correctly.
    """
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database query failed while executing smoke test")
        raise HTTPException(status_code=503, detail="Database unavailable")
    return HealthResponseSchema(status="ok", database="ok")
