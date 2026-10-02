from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    RESTAURANT_OWNER = "RESTAURANT_OWNER"
    STAFF = "STAFF"
    CUSTOMER = "CUSTOMER"
    DRIVER = "DRIVER"


class ContactMethod(StrEnum):
    PHONE = "PHONE"
    EMAIL = "EMAIL"


class RestaurantStaffRole(StrEnum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"
    STAFF = "STAFF"


class CartStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CHECKED_OUT = "CHECKED_OUT"


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    PREPARING = "PREPARING"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class RefundStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class DeliveryStatus(StrEnum):
    UNASSIGNED = "UNASSIGNED"
    ASSIGNED = "ASSIGNED"
    PICKED_UP = "PICKED_UP"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
