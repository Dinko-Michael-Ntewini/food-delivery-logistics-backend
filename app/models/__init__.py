"""Import every model so SQLAlchemy and Alembic load complete metadata."""
from app.models.delivery import Delivery, DeliveryStatusHistory, Driver
from app.models.identity import Address, CustomerProfile, User
from app.models.ordering import Cart, CartItem, Order, OrderItem, OrderStatusHistory
from app.models.payment import Payment, Refund
from app.models.restaurant import Category, Menu, Product, ProductVariant, Restaurant, RestaurantBranch, RestaurantStaff

__all__ = [
    "User", "Address", "CustomerProfile", "Restaurant", "RestaurantBranch", "RestaurantStaff",
    "Menu", "Category", "Product", "ProductVariant", "Cart", "CartItem", "Order", "OrderItem",
    "OrderStatusHistory", "Payment", "Refund", "Driver", "Delivery", "DeliveryStatusHistory",
]
