from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Self

import httpx
import pytest

from app.models.transactions import Currency, Transaction, TransactionStatus
from app.schemas.transactions import TransactionCreate
from app.services import transactions_service


@dataclass
class FakeSession:
    transaction: Transaction
    committed: bool = False
    rolled_back: bool = False

    async def get(self, model, transaction_id):
        return self.transaction

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeClient:
    def __init__(self, failed_attempt: int | None) -> None:
        self.failed_attempt = failed_attempt
        self.calls = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args) -> None:
        return None

    async def get(self, url: str) -> httpx.Response:
        self.calls += 1
        status_code = 500 if self.calls == self.failed_attempt else 200
        request = httpx.Request("GET", url)
        return httpx.Response(status_code, request=request)


def make_transaction() -> Transaction:
    return Transaction(
        transaction_id="txn_worker_test",
        source_account="source_1",
        destination_account="destination_1",
        amount=Decimal("10.00"),
        currency=Currency.USD,
        status=TransactionStatus.PROCESSING,
        created_at=datetime.now(UTC),
        processed_at=None,
    )


class NoInsertResult:
    def scalar_one_or_none(self) -> None:
        return None


@dataclass
class FakeDuplicateSession:
    transaction: Transaction
    committed: bool = False
    selected: bool = False

    async def execute(self, statement) -> NoInsertResult:
        return NoInsertResult()

    async def commit(self) -> None:
        self.committed = True

    async def scalar(self, statement) -> Transaction:
        self.selected = True
        return self.transaction


@pytest.mark.asyncio
async def test_duplicate_returns_authoritative_processed_status() -> None:
    transaction = make_transaction()
    transaction.status = TransactionStatus.PROCESSED
    transaction.processed_at = datetime.now(UTC)
    session = FakeDuplicateSession(transaction)
    payload = TransactionCreate(
        transaction_id=transaction.transaction_id,
        source_account=transaction.source_account,
        destination_account=transaction.destination_account,
        amount=transaction.amount,
        currency=transaction.currency,
    )

    returned, created = await transactions_service.create_or_get_transaction(
        session,  # type: ignore[arg-type]
        payload,
    )

    assert created is False
    assert returned.status == TransactionStatus.PROCESSED
    assert session.committed is True
    assert session.selected is True


@pytest.mark.parametrize(
    ("failed_attempt", "expected_status"),
    [
        (None, TransactionStatus.PROCESSED),
        (3, TransactionStatus.FAILED),
    ],
)
@pytest.mark.asyncio
async def test_background_processing_persists_final_status(
    monkeypatch: pytest.MonkeyPatch,
    failed_attempt: int | None,
    expected_status: TransactionStatus,
) -> None:
    transaction = make_transaction()
    session = FakeSession(transaction)
    client = FakeClient(failed_attempt)
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    @asynccontextmanager
    async def fake_session_factory() -> AsyncIterator[FakeSession]:
        yield session

    monkeypatch.setattr(transactions_service.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        transactions_service.httpx,
        "AsyncClient",
        lambda **kwargs: client,
    )
    monkeypatch.setattr(
        transactions_service,
        "AsyncSessionLocal",
        fake_session_factory,
    )

    await transactions_service.process_transaction(transaction.transaction_id)

    assert client.calls == 5
    assert sum(delays) == 30
    assert transaction.status == expected_status
    assert transaction.processed_at is not None
    assert session.committed is True
    assert session.rolled_back is False
