from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ContactMethod, UserRole
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.delivery import Driver
    from app.models.ordering import OrderStatusHistory
    from app.models.restaurant import RestaurantStaff


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    customer_profile: Mapped["CustomerProfile | None"] = relationship(back_populates="user", uselist=False)
    addresses: Mapped[list["Address"]] = relationship(back_populates="user")
    restaurant_memberships: Mapped[list["RestaurantStaff"]] = relationship(back_populates="user")
    driver_profile: Mapped["Driver | None"] = relationship(back_populates="user", uselist=False)
    order_status_changes: Mapped[list["OrderStatusHistory"]] = relationship(back_populates="changed_by_user", foreign_keys="OrderStatusHistory.changed_by_user_id")


class Address(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "addresses"
    __table_args__ = (Index("ix_addresses_user_default", "user_id", "is_default"), Index("uq_addresses_one_default_per_user", "user_id", unique=True, sqlite_where=text("is_default = 1"), postgresql_where=text("is_default = true")),)
    user_id: Mapped[object] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    recipient_name: Mapped[str] = mapped_column(String(150), nullable=False)
    recipient_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    line1: Mapped[str] = mapped_column(String(180), nullable=False)
    line2: Mapped[str | None] = mapped_column(String(180))
    landmark: Mapped[str | None] = mapped_column(String(180))
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    user: Mapped[User] = relationship(back_populates="addresses")
    orders: Mapped[list["Order"]] = relationship(back_populates="delivery_address")


class CustomerProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customer_profiles"
    user_id: Mapped[object] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), unique=True, nullable=False)
    preferred_contact_method: Mapped[ContactMethod | None] = mapped_column(Enum(ContactMethod, native_enum=False))
    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    user: Mapped[User] = relationship(back_populates="customer_profile")
    carts: Mapped[list["Cart"]] = relationship(back_populates="customer")
    orders: Mapped[list["Order"]] = relationship(back_populates="customer")
