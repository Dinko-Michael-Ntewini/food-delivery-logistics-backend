from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import DeliveryStatus
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.identity import User
    from app.models.ordering import Order


class Driver(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "drivers"
    user_id: Mapped[object] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), unique=True, nullable=False)
    vehicle_type: Mapped[str] = mapped_column(String(50), nullable=False)
    vehicle_identifier: Mapped[str | None] = mapped_column(String(80), unique=True)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    user: Mapped["User"] = relationship(back_populates="driver_profile")
    deliveries: Mapped[list["Delivery"]] = relationship(back_populates="driver")


class Delivery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deliveries"
    order_id: Mapped[object] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), unique=True, nullable=False)
    driver_id: Mapped[object | None] = mapped_column(ForeignKey("drivers.id", ondelete="RESTRICT"), index=True)
    status: Mapped[DeliveryStatus] = mapped_column(Enum(DeliveryStatus, native_enum=False), nullable=False, default=DeliveryStatus.UNASSIGNED)
    assigned_at: Mapped[datetime | None] = mapped_column()
    picked_up_at: Mapped[datetime | None] = mapped_column()
    delivered_at: Mapped[datetime | None] = mapped_column()
    order: Mapped["Order"] = relationship(back_populates="delivery")
    driver: Mapped["Driver | None"] = relationship(back_populates="deliveries")
    status_history: Mapped[list["DeliveryStatusHistory"]] = relationship(back_populates="delivery")


class DeliveryStatusHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "delivery_status_history"
    __table_args__ = (Index("ix_delivery_status_history_delivery_created", "delivery_id", "created_at"),)
    delivery_id: Mapped[object] = mapped_column(ForeignKey("deliveries.id", ondelete="RESTRICT"), nullable=False)
    from_status: Mapped[DeliveryStatus | None] = mapped_column(Enum(DeliveryStatus, native_enum=False))
    to_status: Mapped[DeliveryStatus] = mapped_column(Enum(DeliveryStatus, native_enum=False), nullable=False)
    changed_by_user_id: Mapped[object | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    delivery: Mapped[Delivery] = relationship(back_populates="status_history")
    changed_by_user: Mapped["User | None"] = relationship(foreign_keys=[changed_by_user_id])
