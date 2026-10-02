from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import PaymentStatus, RefundStatus
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.ordering import Order


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount >= 0", name="amount_nonnegative"),)
    order_id: Mapped[object] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(150), unique=True)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus, native_enum=False), nullable=False, default=PaymentStatus.PENDING)
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    order: Mapped["Order"] = relationship(back_populates="payments")
    refunds: Mapped[list["Refund"]] = relationship(back_populates="payment")


class Refund(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "refunds"
    __table_args__ = (CheckConstraint("amount >= 0", name="amount_nonnegative"),)
    payment_id: Mapped[object] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(150), unique=True)
    status: Mapped[RefundStatus] = mapped_column(Enum(RefundStatus, native_enum=False), nullable=False, default=RefundStatus.PENDING)
    payment: Mapped[Payment] = relationship(back_populates="refunds")
