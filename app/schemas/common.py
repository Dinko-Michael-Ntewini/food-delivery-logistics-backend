from datetime import datetime
from uuid import UUID
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TimestampSchema(ORMModel):
    id: UUID
    created_at: datetime
    updated_at: datetime


class PaginationMeta(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)


T = TypeVar("T")


class Page(PaginationMeta, Generic[T]):
    items: list[T]
