from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import RestaurantStaffRole
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.identity import User
    from app.models.ordering import Cart, Order


class Restaurant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "restaurants"
    __table_args__ = (Index("ix_restaurants_active_slug", "is_active", "slug"),)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(254))
    contact_phone: Mapped[str | None] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    branches: Mapped[list["RestaurantBranch"]] = relationship(back_populates="restaurant")
    staff_memberships: Mapped[list["RestaurantStaff"]] = relationship(back_populates="restaurant")
    menus: Mapped[list["Menu"]] = relationship(back_populates="restaurant")


class RestaurantBranch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "restaurant_branches"
    __table_args__ = (UniqueConstraint("restaurant_id", "name"), Index("ix_branches_restaurant_active_city", "restaurant_id", "is_active", "city"))
    restaurant_id: Mapped[object] = mapped_column(ForeignKey("restaurants.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(254))
    line1: Mapped[str] = mapped_column(String(180), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    restaurant: Mapped[Restaurant] = relationship(back_populates="branches")
    staff_memberships: Mapped[list["RestaurantStaff"]] = relationship(back_populates="branch")
    carts: Mapped[list["Cart"]] = relationship(back_populates="branch")
    orders: Mapped[list["Order"]] = relationship(back_populates="branch")


class RestaurantStaff(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "restaurant_staff"
    __table_args__ = (
        Index("uq_restaurant_staff_global_member", "restaurant_id", "user_id", unique=True, sqlite_where=text("branch_id IS NULL"), postgresql_where=text("branch_id IS NULL")),
        Index("uq_restaurant_staff_branch_member", "restaurant_id", "user_id", "branch_id", unique=True, sqlite_where=text("branch_id IS NOT NULL"), postgresql_where=text("branch_id IS NOT NULL")),
    )
    restaurant_id: Mapped[object] = mapped_column(ForeignKey("restaurants.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[object] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[object | None] = mapped_column(ForeignKey("restaurant_branches.id", ondelete="RESTRICT"))
    staff_role: Mapped[RestaurantStaffRole] = mapped_column(Enum(RestaurantStaffRole, native_enum=False), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    restaurant: Mapped[Restaurant] = relationship(back_populates="staff_memberships")
    user: Mapped["User"] = relationship(back_populates="restaurant_memberships")
    branch: Mapped[RestaurantBranch | None] = relationship(back_populates="staff_memberships")


class Menu(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "menus"
    __table_args__ = (UniqueConstraint("restaurant_id", "name"),)
    restaurant_id: Mapped[object] = mapped_column(ForeignKey("restaurants.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    restaurant: Mapped[Restaurant] = relationship(back_populates="menus")
    categories: Mapped[list["Category"]] = relationship(back_populates="menu")


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("menu_id", "name"),)
    menu_id: Mapped[object] = mapped_column(ForeignKey("menus.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    menu: Mapped[Menu] = relationship(back_populates="categories")
    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (CheckConstraint("base_price >= 0", name="base_price_nonnegative"), Index("ix_products_category_available_price", "category_id", "is_available", "base_price"))
    category_id: Mapped[object] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    image_url: Mapped[str | None] = mapped_column(String(2048))
    category: Mapped[Category] = relationship(back_populates="products")
    variants: Mapped[list["ProductVariant"]] = relationship(back_populates="product")


class ProductVariant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_variants"
    __table_args__ = (UniqueConstraint("product_id", "name"), CheckConstraint("price_override IS NULL OR price_override >= 0", name="override_nonnegative"), CheckConstraint("price_delta IS NULL OR price_delta >= 0", name="delta_nonnegative"), CheckConstraint("NOT (price_override IS NOT NULL AND price_delta IS NOT NULL)", name="single_price_adjustment"))
    product_id: Mapped[object] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(80), unique=True)
    price_override: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    price_delta: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    product: Mapped[Product] = relationship(back_populates="variants")
    cart_items: Mapped[list["CartItem"]] = relationship(back_populates="product_variant")
    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="product_variant")
