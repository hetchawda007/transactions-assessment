from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints import transactions as transaction_endpoints
from app.core.config import Settings
from app.db.session import get_db_session
from app.main import app
from app.models.transactions import Currency, Transaction, TransactionStatus


def test_database_url_is_normalized_for_async_usage() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:p@ss@localhost:5432/database"
    )

    assert settings.database_url == (
        "postgresql+asyncpg://user:p%40ss@localhost:5432/database"
    )


@pytest.fixture
def transaction() -> Transaction:
    return Transaction(
        transaction_id="txn_abc123def456",
        source_account="acc_user_789",
        destination_account="acc_merchant_456",
        amount=Decimal("1500.00"),
        currency=Currency.INR,
        status=TransactionStatus.PROCESSING,
        created_at=datetime.now(UTC),
        processed_at=None,
    )


@pytest.fixture
def database_override():
    async def fake_database_session():
        yield object()

    app.dependency_overrides[get_db_session] = fake_database_session
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_check() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "HEALTHY"
    assert response.json()["current_time"].endswith("Z")


@pytest.mark.asyncio
async def test_webhook_accepts_and_schedules_new_transaction(
    monkeypatch: pytest.MonkeyPatch,
    database_override: None,
    transaction: Transaction,
) -> None:
    async def fake_create_or_get(session, payload):
        return transaction, True

    scheduled: list[str] = []
    monkeypatch.setattr(
        transaction_endpoints,
        "create_or_get_transaction",
        fake_create_or_get,
    )
    monkeypatch.setattr(
        transaction_endpoints,
        "schedule_transaction_processing",
        scheduled.append,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/webhooks/transactions",
            json={
                "transaction_id": "txn_abc123def456",
                "source_account": "acc_user_789",
                "destination_account": "acc_merchant_456",
                "amount": 1500,
                "currency": "INR",
            },
        )

    assert response.status_code == 202
    assert response.json()["status"] == "PROCESSING"
    assert response.json()["already_exists"] is False
    assert scheduled == ["txn_abc123def456"]


@pytest.mark.asyncio
async def test_duplicate_webhook_is_not_scheduled_again(
    monkeypatch: pytest.MonkeyPatch,
    database_override: None,
    transaction: Transaction,
) -> None:
    transaction.status = TransactionStatus.PROCESSED
    transaction.processed_at = datetime.now(UTC)

    async def fake_create_or_get(session, payload):
        return transaction, False

    scheduled: list[str] = []
    monkeypatch.setattr(
        transaction_endpoints,
        "create_or_get_transaction",
        fake_create_or_get,
    )
    monkeypatch.setattr(
        transaction_endpoints,
        "schedule_transaction_processing",
        scheduled.append,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/webhooks/transactions",
            json={
                "transaction_id": "txn_abc123def456",
                "source_account": "acc_user_789",
                "destination_account": "acc_merchant_456",
                "amount": "1500.00",
                "currency": "INR",
            },
        )

    assert response.status_code == 202
    assert response.json()["already_exists"] is True
    assert response.json()["status"] == "PROCESSED"
    assert scheduled == []


@pytest.mark.asyncio
async def test_get_transaction(
    monkeypatch: pytest.MonkeyPatch,
    database_override: None,
    transaction: Transaction,
) -> None:
    async def fake_get(session, transaction_id):
        return transaction

    monkeypatch.setattr(transaction_endpoints, "get_transaction_by_id", fake_get)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/transactions/txn_abc123def456")

    body = response.json()
    assert response.status_code == 200
    assert body["transaction_id"] == "txn_abc123def456"
    assert body["amount"] == 1500.0
    assert body["processed_at"] is None


@pytest.mark.asyncio
async def test_get_missing_transaction_returns_404(
    monkeypatch: pytest.MonkeyPatch,
    database_override: None,
) -> None:
    async def fake_get(session, transaction_id):
        return None

    monkeypatch.setattr(transaction_endpoints, "get_transaction_by_id", fake_get)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/transactions/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Transaction 'missing' does not exist"
