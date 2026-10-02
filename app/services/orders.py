"""Atomic checkout, order visibility, and the Stage 6 state machine."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from app.core.exceptions import ApplicationError, ForbiddenError, InvalidTransitionError
from app.core.pagination import paginate, sorted_query

from app.core.enums import CartStatus, OrderStatus, PaymentStatus, RestaurantStaffRole, UserRole
from app.models.identity import Address, CustomerProfile, User
from app.models.ordering import Cart, CartItem, Order, OrderItem, OrderStatusHistory
from app.models.payment import Payment
from app.models.restaurant import Product, ProductVariant, RestaurantBranch, RestaurantStaff
from app.schemas.order import (
    CheckoutRequest, OrderItemOut, OrderOut, OrderPage, OrderStatusHistoryOut,
)
from app.services.cart import unit_price


STATUS_SEQUENCE = (
    OrderStatus.PENDING,
    OrderStatus.CONFIRMED,
    OrderStatus.PREPARING,
    OrderStatus.READY_FOR_PICKUP,
    OrderStatus.OUT_FOR_DELIVERY,
    OrderStatus.DELIVERED,
)
RESTAURANT_TARGETS = frozenset(STATUS_SEQUENCE[1:4])
MAX_MONEY = Decimal("9999999999.99")


def address_snapshot(address: Address) -> dict[str, str | None]:
    return {
        "label": address.label,
        "recipient_name": address.recipient_name,
        "recipient_phone": address.recipient_phone,
        "line1": address.line1,
        "line2": address.line2,
        "landmark": address.landmark,
        "city": address.city,
        "latitude": str(address.latitude) if address.latitude is not None else None,
        "longitude": str(address.longitude) if address.longitude is not None else None,
    }


def order_response(db: Session, order: Order, *, preloaded: bool = False) -> OrderOut:
    items = sorted(order.items, key=lambda row: (row.created_at, row.id)) if preloaded else db.scalars(select(OrderItem).where(OrderItem.order_id == order.id)
                       .order_by(OrderItem.created_at, OrderItem.id)).all()
    history = sorted(order.status_history, key=lambda row: (row.created_at, row.id)) if preloaded else db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id == order.id)
                         .order_by(OrderStatusHistory.created_at, OrderStatusHistory.id)).all()
    payment = min(order.payments, key=lambda row: (row.created_at, row.id), default=None) if preloaded else db.scalar(select(Payment).where(Payment.order_id == order.id)
                        .order_by(Payment.created_at, Payment.id).limit(1))
    return OrderOut(
        id=order.id,
        order_number=order.order_number,
        customer_name=order.customer.user.full_name,
        restaurant_id=order.branch.restaurant_id,
        branch_id=order.branch_id,
        status=order.status,
        subtotal=order.subtotal,
        delivery_fee=order.delivery_fee,
        total_amount=order.total_amount,
        delivery_address_snapshot=order.delivery_address_snapshot,
        items=[OrderItemOut.model_validate({
            "id": item.id, "product_variant_id": item.product_variant_id,
            "product_name_snapshot": item.product_name_snapshot,
            "variant_name_snapshot": item.variant_name_snapshot,
            "unit_price": item.unit_price, "quantity": item.quantity,
            "line_total": item.line_total, "created_at": item.created_at,
        }) for item in items],
        status_history=[OrderStatusHistoryOut.model_validate({
            "id": row.id, "from_status": row.from_status, "to_status": row.to_status,
            "changed_by_user_id": row.changed_by_user_id, "reason": row.reason,
            "created_at": row.created_at,
        }) for row in history],
    payment_status=payment.status if payment else None,
        placed_at=order.placed_at,
        created_at=order.created_at,
    )


def checkout(db: Session, actor: User, payload: CheckoutRequest) -> OrderOut:
    if actor.role != UserRole.CUSTOMER:
        raise HTTPException(403, detail="Customer access required")
    profile = db.scalar(select(CustomerProfile).where(CustomerProfile.user_id == actor.id))
    if profile is None:
        raise HTTPException(409, detail="Cart is empty")
    cart = db.scalar(select(Cart).where(Cart.customer_id == profile.id,
                                       Cart.status == CartStatus.ACTIVE).with_for_update())
    if cart is None:
        raise HTTPException(409, detail="Cart is empty")
    rows = db.scalars(select(CartItem).where(CartItem.cart_id == cart.id)
                      .order_by(CartItem.created_at, CartItem.id).with_for_update()).all()
    if not rows:
        raise HTTPException(409, detail="Cart is empty")
    if cart.branch_id is None:
        raise HTTPException(409, detail="Cart has no branch")
    branch = db.get(RestaurantBranch, cart.branch_id)
    if branch is None or not branch.is_active or not branch.restaurant.is_active:
        raise HTTPException(409, detail="Cart branch unavailable")
    address = db.get(Address, payload.address_id)
    if address is None or address.user_id != actor.id:
        raise HTTPException(404, detail="Address not found")

    snapshots: list[dict] = []
    subtotal = Decimal("0.00")
    for row in rows:
        if row.quantity <= 0:
            raise HTTPException(409, detail="Cart quantity is invalid")
        product = db.get(Product, row.product_id)
        if product is None:
            raise HTTPException(409, detail="Cart product no longer exists")
        category = product.category
        menu = category.menu
        if (not product.is_available or not category.is_active or not menu.is_active
                or not menu.restaurant.is_active):
            raise HTTPException(409, detail="Cart product unavailable")
        if menu.restaurant_id != branch.restaurant_id:
            raise HTTPException(409, detail="Cart product is outside the branch restaurant")
        variant = None
        if row.product_variant_id is not None:
            variant = db.get(ProductVariant, row.product_variant_id)
            if variant is None or variant.product_id != product.id or not variant.is_available:
                raise HTTPException(409, detail="Cart variant unavailable or invalid")
        price = unit_price(product, variant)
        line = price * row.quantity
        subtotal += line
        if price < 0 or line > MAX_MONEY or subtotal > MAX_MONEY:
            raise HTTPException(409, detail="Cart total exceeds supported amount")
        snapshots.append({
            "product_variant_id": variant.id if variant else None,
            "product_name_snapshot": product.name,
            "variant_name_snapshot": variant.name if variant else None,
            "unit_price": price,
            "quantity": row.quantity,
            "line_total": line,
            "notes": row.notes,
        })

    order = Order(
        order_number=uuid4().hex.upper(), customer_id=profile.id, branch_id=branch.id,
        delivery_address_id=address.id, delivery_address_snapshot=address_snapshot(address),
        status=OrderStatus.PENDING, subtotal=subtotal,
        delivery_fee=Decimal("0.00"), total_amount=subtotal,
    )
    try:
        db.add(order)
        db.flush()
        db.add_all(OrderItem(order_id=order.id, **data) for data in snapshots)
        db.add(OrderStatusHistory(order_id=order.id, from_status=None,
                                  to_status=OrderStatus.PENDING,
                                  changed_by_user_id=actor.id, reason="Checkout",
                                  created_at=datetime.now(timezone.utc)))
        db.add(Payment(order_id=order.id, amount=subtotal, currency="GHS",
                       provider=payload.payment_method, status=PaymentStatus.PENDING))
        for row in rows:
            db.delete(row)
        cart.branch_id = None
        db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="Checkout conflicted with current data; retry") from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(order)
    return order_response(db, order)


def membership_filter(actor: User):
    allowed_roles = ([RestaurantStaffRole.OWNER] if actor.role == UserRole.RESTAURANT_OWNER
                     else [RestaurantStaffRole.MANAGER, RestaurantStaffRole.STAFF])
    scope = RestaurantStaff.branch_id.is_(None) if actor.role == UserRole.RESTAURANT_OWNER else or_(
        RestaurantStaff.branch_id.is_(None), RestaurantStaff.branch_id == Order.branch_id)
    return exists(select(RestaurantStaff.id).where(
        RestaurantStaff.user_id == actor.id,
        RestaurantStaff.restaurant_id == RestaurantBranch.restaurant_id,
        RestaurantStaff.is_active.is_(True),
        RestaurantStaff.staff_role.in_(allowed_roles), scope,
    ))


def visible_orders_query(actor: User):
    query = select(Order)
    if actor.role == UserRole.ADMIN:
        return query
    if actor.role == UserRole.CUSTOMER:
        return query.join(CustomerProfile).where(CustomerProfile.user_id == actor.id)
    if actor.role in (UserRole.RESTAURANT_OWNER, UserRole.STAFF):
        return query.join(RestaurantBranch, Order.branch_id == RestaurantBranch.id).where(
            membership_filter(actor))
    raise HTTPException(403, detail="Order access denied")


def list_orders(db: Session, actor: User, page: int, page_size: int,
                status: OrderStatus | None, *, restaurant_id: UUID | None = None,
                branch_id: UUID | None = None, customer_id: UUID | None = None,
                date_from: datetime | None = None, date_to: datetime | None = None,
                sort: str = "-placed_at", search: str | None = None) -> OrderPage:
    query = visible_orders_query(actor)
    if search:
        query = query.where(Order.order_number.ilike(f"%{search}%"))
    if customer_id is not None:
        if actor.role != UserRole.ADMIN:
            raise ForbiddenError("Customer filtering requires administrator access")
        query = query.where(Order.customer_id == customer_id)
    if restaurant_id is not None:
        query = query.where(Order.branch.has(RestaurantBranch.restaurant_id == restaurant_id))
    if branch_id is not None:
        query = query.where(Order.branch_id == branch_id)
    date_from = normalize_utc(date_from)
    date_to = normalize_utc(date_to)
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ApplicationError("date_from must not exceed date_to")
    if date_from is not None:
        query = query.where(Order.placed_at >= date_from)
    if date_to is not None:
        query = query.where(Order.placed_at <= date_to)
    if status is not None:
        query = query.where(Order.status == status)
    query = sorted_query(query, sort, {"placed_at": Order.placed_at, "created_at": Order.created_at,
                         "updated_at": Order.updated_at, "total": Order.total_amount,
                         "status": Order.status}, Order.id).options(
        selectinload(Order.items), selectinload(Order.status_history), selectinload(Order.payments),
        selectinload(Order.customer).selectinload(CustomerProfile.user), selectinload(Order.branch))
    result = paginate(db, query, page, page_size)
    result["items"] = [order_response(db, row, preloaded=True) for row in result["items"]]
    return OrderPage(**result)


def normalize_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def accessible_order(db: Session, actor: User, order_id: UUID) -> Order:
    query = visible_orders_query(actor).where(Order.id == order_id)
    order = db.scalar(query)
    if order is None:
        raise HTTPException(404, detail="Order not found")
    return order


def apply_order_transition(db: Session, actor: User, order: Order,
                           target: OrderStatus, reason: str | None) -> None:
    """Apply the authoritative next-state rule without committing the caller's transaction."""
    current_index = STATUS_SEQUENCE.index(order.status)
    if current_index == len(STATUS_SEQUENCE) - 1 or target != STATUS_SEQUENCE[current_index + 1]:
        raise InvalidTransitionError("Invalid order status transition")
    previous = order.status
    order.status = target
    db.add(OrderStatusHistory(order_id=order.id, from_status=previous,
                              to_status=target, changed_by_user_id=actor.id,
                              reason=reason, created_at=datetime.now(timezone.utc)))


def transition_order(db: Session, actor: User, order_id: UUID,
                     target: OrderStatus, reason: str | None) -> OrderOut:
    order = accessible_order(db, actor, order_id)
    if actor.role == UserRole.CUSTOMER:
        raise HTTPException(403, detail="Customers cannot change order status")
    if actor.role != UserRole.ADMIN and target not in RESTAURANT_TARGETS:
        raise HTTPException(403, detail="Use the assigned delivery workflow for delivery transitions")
    try:
        db.execute(select(Order.id).where(Order.id == order.id).with_for_update()).first()
        db.refresh(order)
        from app.models.delivery import Delivery
        if target in (OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED) and db.scalar(
                select(Delivery.id).where(Delivery.order_id == order.id)) is not None:
            raise HTTPException(409, detail="Transition the linked Delivery to keep statuses synchronized")
        apply_order_transition(db, actor, order, target, reason)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="Order status changed concurrently; retry") from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(order)
    return order_response(db, order)
