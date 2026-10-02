"""Stage 6 order request and response contracts."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import OrderStatus, PaymentStatus
from app.schemas.common import Page


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address_id: UUID
    payment_method: Literal["CASH_ON_DELIVERY", "MOBILE_MONEY"]


class OrderStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: OrderStatus
    reason: str | None = Field(default=None, max_length=500)


class OrderItemOut(BaseModel):
    id: UUID
    product_variant_id: UUID | None
    product_name_snapshot: str
    variant_name_snapshot: str | None
    unit_price: Decimal
    quantity: int
    line_total: Decimal
    created_at: datetime


class OrderStatusHistoryOut(BaseModel):
    id: UUID
    from_status: OrderStatus | None
    to_status: OrderStatus
    changed_by_user_id: UUID | None
    reason: str | None
    created_at: datetime


class OrderOut(BaseModel):
    id: UUID
    order_number: str
    customer_name: str
    restaurant_id: UUID
    branch_id: UUID
    status: OrderStatus
    subtotal: Decimal
    delivery_fee: Decimal
    total_amount: Decimal
    delivery_address_snapshot: dict[str, str | None]
    items: list[OrderItemOut]
    status_history: list[OrderStatusHistoryOut]
    payment_status: PaymentStatus | None
    placed_at: datetime
    created_at: datetime


class OrderPage(Page[OrderOut]):
    pass
