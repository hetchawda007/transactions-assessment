import asyncio
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.transactions import Transaction, TransactionStatus
from app.schemas.transactions import TransactionCreate

logger = logging.getLogger(__name__)

EXTERNAL_CALL_COUNT = 5
PROCESSING_DURATION_SECONDS = 30.0

_background_tasks: set[asyncio.Task[None]] = set()


async def create_or_get_transaction(
    session: AsyncSession,
    payload: TransactionCreate,
) -> tuple[Transaction, bool]:
    """Atomically create a transaction, returning whether this call inserted it."""
    statement = (
        insert(Transaction)
        .values(
            transaction_id=payload.transaction_id,
            source_account=payload.source_account,
            destination_account=payload.destination_account,
            amount=payload.amount,
            currency=payload.currency,
            status=TransactionStatus.PROCESSING,
        )
        .on_conflict_do_nothing(index_elements=[Transaction.transaction_id])
        .returning(Transaction.transaction_id)
    )

    result = await session.execute(statement)
    created = result.scalar_one_or_none() is not None
    await session.commit()

    # Always reload the authoritative row. In particular, a conflicting insert
    # must return the status currently persisted by the background worker.
    transaction = await session.scalar(
        select(Transaction)
        .where(Transaction.transaction_id == payload.transaction_id)
        .execution_options(populate_existing=True)
    )

    if transaction is None:  # Defensive guard for an unexpected database race.
        raise RuntimeError("Transaction was not available after insert conflict")

    return transaction, created


async def get_transaction_by_id(
    session: AsyncSession,
    transaction_id: str,
) -> Transaction | None:
    return await session.get(Transaction, transaction_id)


async def process_transaction(transaction_id: str) -> None:
    """Run five external checks over at least 30 seconds and persist the result."""
    request_failed = False
    interval = PROCESSING_DURATION_SECONDS / EXTERNAL_CALL_COUNT

    async with httpx.AsyncClient(
        timeout=settings.external_request_timeout_seconds
    ) as client:
        for attempt in range(1, EXTERNAL_CALL_COUNT + 1):
            await asyncio.sleep(interval)
            try:
                response = await client.get(settings.external_api_url)
                response.raise_for_status()
            except httpx.HTTPError:
                request_failed = True
                logger.exception(
                    "External check %s/%s failed for transaction %s",
                    attempt,
                    EXTERNAL_CALL_COUNT,
                    transaction_id,
                )

    final_status = (
        TransactionStatus.FAILED
        if request_failed
        else TransactionStatus.PROCESSED
    )

    async with AsyncSessionLocal() as session:
        try:
            transaction = await session.get(Transaction, transaction_id)
            if transaction is None:
                logger.error("Transaction %s disappeared during processing", transaction_id)
                return

            transaction.status = final_status
            transaction.processed_at = datetime.now(UTC)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Could not persist result for transaction %s", transaction_id)


def _task_finished(task: asyncio.Task[None]) -> None:
    _background_tasks.discard(task)
    if task.cancelled():
        return
    exception = task.exception()
    if exception is not None:
        logger.error(
            "Transaction background task failed",
            exc_info=(type(exception), exception, exception.__traceback__),
        )


def schedule_transaction_processing(transaction_id: str) -> None:
    task = asyncio.create_task(
        process_transaction(transaction_id),
        name=f"process-transaction-{transaction_id}",
    )
    _background_tasks.add(task)
    task.add_done_callback(_task_finished)


async def recover_processing_transactions() -> None:
    """Resume transactions left PROCESSING after an application restart."""
    async with AsyncSessionLocal() as session:
        result = await session.scalars(
            select(Transaction.transaction_id).where(
                Transaction.status == TransactionStatus.PROCESSING
            )
        )
        transaction_ids = list(result)

    for transaction_id in transaction_ids:
        schedule_transaction_processing(transaction_id)

    if transaction_ids:
        logger.info("Recovered %s unfinished transactions", len(transaction_ids))


async def stop_background_tasks() -> None:
    tasks = list(_background_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
