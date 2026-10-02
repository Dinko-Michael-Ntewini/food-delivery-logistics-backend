from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DriverCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    user_id: UUID
    vehicle_type: str = Field(min_length=1, max_length=50)
    vehicle_identifier: str | None = Field(default=None, min_length=1, max_length=80)
    is_available: bool = True


class DriverUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    vehicle_type: str | None = Field(default=None, min_length=1, max_length=50)
    vehicle_identifier: str | None = Field(default=None, min_length=1, max_length=80)
    is_available: bool | None = None

    @model_validator(mode="after")
    def nonnullable_fields(self):
        for field in ("vehicle_type", "is_available"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class DriverResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: UUID
    vehicle_type: str
    vehicle_identifier: str | None
    is_available: bool
    created_at: datetime
    updated_at: datetime
