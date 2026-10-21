from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, Numeric, String, func
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Currency(str, Enum):
    INR = "INR"
    USD = "USD"
    POUNDS = "POUNDS"


class TransactionStatus(str, Enum):
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
    )

    transaction_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    source_account: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    destination_account: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[Currency] = mapped_column(
        SqlEnum(Currency, name="currency"), nullable=False
    )
    status: Mapped[TransactionStatus] = mapped_column(
        SqlEnum(TransactionStatus, name="transaction_status"),
        nullable=False,
        default=TransactionStatus.PROCESSING,
        server_default=TransactionStatus.PROCESSING.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
