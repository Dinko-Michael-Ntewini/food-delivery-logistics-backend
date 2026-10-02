from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CartItemCreate(BaseModel):
    product_id: UUID
    product_variant_id: UUID | None = None
    quantity: int = Field(gt=0)
    branch_id: UUID | None = None


class CartItemUpdate(BaseModel):
    quantity: int = Field(gt=0)


class CartItemOut(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str
    product_variant_id: UUID | None
    variant_name: str | None
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    product_available: bool
    variant_available: bool | None


class CartOut(BaseModel):
    id: UUID
    branch_id: UUID | None
    restaurant_id: UUID | None
    items: list[CartItemOut]
    subtotal: Decimal
