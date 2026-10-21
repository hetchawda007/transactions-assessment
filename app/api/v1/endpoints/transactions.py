from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.transactions import Transaction
from app.schemas.transactions import (
    TransactionAcceptedResponse,
    TransactionCreate,
    TransactionResponse,
)
from app.services.transactions_service import (
    create_or_get_transaction,
    get_transaction_by_id,
    schedule_transaction_processing,
)

router = APIRouter()


@router.post(
    "/webhooks/transactions",
    response_model=TransactionAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_transaction_webhook(
    payload: TransactionCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TransactionAcceptedResponse:
    transaction, created = await create_or_get_transaction(session, payload)

    if created:
        schedule_transaction_processing(transaction.transaction_id)

    return TransactionAcceptedResponse(
        transaction_id=transaction.transaction_id,
        status=transaction.status,
        already_exists=not created,
        message=(
            "Transaction already exists; returning its current status"
            if not created
            else "Transaction accepted for processing"
        ),
    )


@router.get(
    "/transactions/{transaction_id}",
    response_model=TransactionResponse,
)
async def get_transaction(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    transaction_id: str = Path(
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
) -> Transaction:
    transaction = await get_transaction_by_id(session, transaction_id)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction '{transaction_id}' does not exist",
        )
    return transaction
