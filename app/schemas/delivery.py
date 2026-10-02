from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import DeliveryStatus


class DeliveryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, max_length=500)


class DeliveryAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")
    driver_id: UUID


class DeliveryTransition(DeliveryCreate):
    status: DeliveryStatus


class DeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    order_id: UUID
    driver_id: UUID | None
    status: DeliveryStatus
    assigned_at: datetime | None
    picked_up_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DeliveryHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    delivery_id: UUID
    from_status: DeliveryStatus | None
    to_status: DeliveryStatus
    changed_by_user_id: UUID | None
    note: str | None
    created_at: datetime
