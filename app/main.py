from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.api.v1.endpoints.health import router as health_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import close_db_connection, initialize_database
from app.services.transactions_service import (
    recover_processing_transactions,
    stop_background_tasks,
)

configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await initialize_database()
    await recover_processing_transactions()
    try:
        yield
    finally:
        await stop_background_tasks()
        await close_db_connection()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)
app.include_router(health_router)
app.include_router(api_router)
