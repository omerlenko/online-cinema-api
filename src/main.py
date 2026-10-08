import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Depends
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from sqlalchemy import text
from fastapi.responses import HTMLResponse

from src.accounts.dependencies import validate_docs_credentials
from src.accounts.router import router as accounts_router
from src.core.config import get_settings
from src.database.session import DbDep
from src.core.schemas import HealthResponseSchema, ErrorResponseSchema

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
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


@app.get(
    "/openapi.json",
    dependencies=[Depends(validate_docs_credentials)],
    include_in_schema=False,
)
async def custom_openapi_json() -> dict[str, Any]:
    return app.openapi()


@app.get(
    "/docs", dependencies=[Depends(validate_docs_credentials)], include_in_schema=False
)
async def custom_swagger_ui_html() -> HTMLResponse:
    return get_swagger_ui_html(openapi_url="/openapi.json", title=app.title)


@app.get(
    "/redoc", dependencies=[Depends(validate_docs_credentials)], include_in_schema=False
)
async def custom_redoc_ui_html() -> HTMLResponse:
    return get_redoc_html(openapi_url="/openapi.json", title=app.title)
