from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, JSON, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import CartStatus, OrderStatus
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.identity import Address, CustomerProfile, User
    from app.models.restaurant import ProductVariant, RestaurantBranch
    from app.models.delivery import Delivery
    from app.models.payment import Payment


class Cart(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "carts"
    __table_args__ = (Index("uq_carts_one_active_per_customer", "customer_id", unique=True, sqlite_where=text("status = 'ACTIVE'"), postgresql_where=text("status = 'ACTIVE'")),)
    customer_id: Mapped[object] = mapped_column(ForeignKey("customer_profiles.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[object | None] = mapped_column(ForeignKey("restaurant_branches.id", ondelete="RESTRICT"))
    status: Mapped[CartStatus] = mapped_column(Enum(CartStatus, native_enum=False), nullable=False, default=CartStatus.ACTIVE)
    customer: Mapped["CustomerProfile"] = relationship(back_populates="carts")
    branch: Mapped["RestaurantBranch"] = relationship(back_populates="carts")
    items: Mapped[list["CartItem"]] = relationship(back_populates="cart", cascade="all, delete-orphan")


class CartItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        Index("uq_cart_item_plain_product", "cart_id", "product_id", unique=True, sqlite_where=text("product_variant_id IS NULL"), postgresql_where=text("product_variant_id IS NULL")),
        Index("uq_cart_item_variant", "cart_id", "product_variant_id", unique=True, sqlite_where=text("product_variant_id IS NOT NULL"), postgresql_where=text("product_variant_id IS NOT NULL")),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )
    cart_id: Mapped[object] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[object] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    product_variant_id: Mapped[object | None] = mapped_column(ForeignKey("product_variants.id", ondelete="RESTRICT"))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500))
    cart: Mapped[Cart] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()
    product_variant: Mapped["ProductVariant"] = relationship(back_populates="cart_items")


class Order(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("subtotal >= 0", name="subtotal_nonnegative"),
        CheckConstraint("delivery_fee >= 0", name="delivery_fee_nonnegative"),
        CheckConstraint("total_amount >= 0", name="total_nonnegative"),
        Index("ix_orders_customer_status_placed", "customer_id", "status", "placed_at"),
        Index("ix_orders_branch_status_placed", "branch_id", "status", "placed_at"),
    )
    order_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    customer_id: Mapped[object] = mapped_column(ForeignKey("customer_profiles.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[object] = mapped_column(ForeignKey("restaurant_branches.id", ondelete="RESTRICT"), nullable=False)
    delivery_address_id: Mapped[object | None] = mapped_column(ForeignKey("addresses.id", ondelete="RESTRICT"))
    delivery_address_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, native_enum=False), nullable=False, default=OrderStatus.PENDING)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    customer_note: Mapped[str | None] = mapped_column(String(500))
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    customer: Mapped["CustomerProfile"] = relationship(back_populates="orders")
    branch: Mapped["RestaurantBranch"] = relationship(back_populates="orders")
    delivery_address: Mapped["Address | None"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order")
    status_history: Mapped[list["OrderStatusHistory"]] = relationship(back_populates="order")
    payments: Mapped[list["Payment"]] = relationship(back_populates="order")
    delivery: Mapped["Delivery | None"] = relationship(back_populates="order", uselist=False)


class OrderItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("unit_price >= 0", name="unit_price_nonnegative"), CheckConstraint("quantity > 0", name="quantity_positive"), CheckConstraint("line_total >= 0", name="line_total_nonnegative"))
    order_id: Mapped[object] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    product_variant_id: Mapped[object | None] = mapped_column(ForeignKey("product_variants.id", ondelete="SET NULL"))
    product_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    variant_name_snapshot: Mapped[str | None] = mapped_column(String(120))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    order: Mapped[Order] = relationship(back_populates="items")
    product_variant: Mapped["ProductVariant | None"] = relationship(back_populates="order_items")


class OrderStatusHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "order_status_history"
    __table_args__ = (Index("ix_order_status_history_order_created", "order_id", "created_at"),)
    order_id: Mapped[object] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    from_status: Mapped[OrderStatus | None] = mapped_column(Enum(OrderStatus, native_enum=False))
    to_status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, native_enum=False), nullable=False)
    changed_by_user_id: Mapped[object | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    order: Mapped[Order] = relationship(back_populates="status_history")
    changed_by_user: Mapped["User | None"] = relationship(back_populates="order_status_changes", foreign_keys=[changed_by_user_id])
