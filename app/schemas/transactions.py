from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.transactions import Currency, TransactionStatus

IDENTIFIER_PATTERN = r"^[A-Za-z0-9_-]+$"


class TransactionCreate(BaseModel):
    transaction_id: str = Field(
        min_length=1,
        max_length=255,
        pattern=IDENTIFIER_PATTERN,
    )
    source_account: str = Field(
        min_length=1,
        max_length=255,
        pattern=IDENTIFIER_PATTERN,
    )
    destination_account: str = Field(
        min_length=1,
        max_length=255,
        pattern=IDENTIFIER_PATTERN,
    )
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: Currency

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @model_validator(mode="after")
    def accounts_must_differ(self) -> "TransactionCreate":
        if self.source_account == self.destination_account:
            raise ValueError("source_account and destination_account must differ")
        return self


class TransactionAcceptedResponse(BaseModel):
    transaction_id: str
    status: TransactionStatus
    already_exists: bool
    message: str


class TransactionResponse(BaseModel):
    transaction_id: str
    source_account: str
    destination_account: str
    amount: float
    currency: Currency
    status: TransactionStatus
    created_at: datetime
    processed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
