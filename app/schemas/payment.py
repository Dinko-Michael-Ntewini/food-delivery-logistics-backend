"""Safe Stage 7 financial API contracts."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import PaymentStatus, RefundStatus


class PaymentCreate(BaseModel):
    """Resolve the Payment already created atomically by checkout."""
    model_config = ConfigDict(extra="forbid")
    order_id: UUID


class PaymentResponse(BaseModel):
    id: UUID
    order_id: UUID
    amount: Decimal
    currency: str
    method: str
    status: PaymentStatus
    reference: str | None
    paid_at: datetime | None
    created_at: datetime
    updated_at: datetime
    total_refunded: Decimal
    remaining_refundable: Decimal


class RefundCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Refund reason cannot be blank")
        return stripped


class RefundResponse(BaseModel):
    id: UUID
    payment_id: UUID
    amount: Decimal
    reason: str
    status: RefundStatus
    reference: str | None
    created_at: datetime
    updated_at: datetime
