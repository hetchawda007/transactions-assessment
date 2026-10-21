from fastapi import APIRouter

from app.api.v1.endpoints import transactions

router = APIRouter()
router.include_router(transactions.router)
