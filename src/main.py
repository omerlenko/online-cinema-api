import logging

from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from src.database.session import DbDep
from src.core.schemas import HealthResponseSchema

app = FastAPI()

logger = logging.getLogger(__name__)


@app.get("/health", responses={503: {"description": "Database unavailable"}})
async def health(db: DbDep) -> HealthResponseSchema:
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database query failed while executing smoke test")
        raise HTTPException(status_code=503, detail="Database unavailable")
    return HealthResponseSchema(status="ok", database="ok")
