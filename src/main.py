import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from fastapi.responses import HTMLResponse, JSONResponse

from src.core.rate_limit import limiter
from src.accounts.dependencies import validate_docs_credentials
from src.accounts.router import router as accounts_router
from src.movies.router import router as movies_router
from src.cart.router import router as cart_router
from src.orders.router import router as orders_router
from src.payments.router import router as payments_router
from src.core.config import get_settings
from src.database.session import DbDep
from src.core.schemas import HealthResponseSchema, ErrorResponseSchema

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.state.limiter = limiter
settings = get_settings()
api_version_prefix = settings.API_VERSION_PREFIX
app.include_router(
    accounts_router, prefix=f"{api_version_prefix}/accounts", tags=["accounts"]
)
app.include_router(movies_router, prefix=f"{api_version_prefix}/movies")
app.include_router(cart_router, prefix=f"{api_version_prefix}/cart", tags=["cart"])
app.include_router(
    orders_router, prefix=f"{api_version_prefix}/orders", tags=["orders"]
)
app.include_router(
    payments_router, prefix=f"{api_version_prefix}/payments", tags=["payments"]
)

logger = logging.getLogger(__name__)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    return JSONResponse(
        content={"detail": f"Rate limit exceeded: {exc.detail}"}, status_code=429
    )


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
