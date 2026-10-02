"""Delivery dispatch and atomic synchronization with the authoritative order engine."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import DeliveryStatus, OrderStatus, UserRole
from app.core.exceptions import InvalidTransitionError
from app.models.delivery import Delivery, DeliveryStatusHistory, Driver
from app.models.identity import User
from app.models.ordering import Order
from app.services.drivers import active_delivery, own_driver
from app.services.orders import accessible_order, apply_order_transition, visible_orders_query

NEXT_STATUS = {
    DeliveryStatus.ASSIGNED: DeliveryStatus.PICKED_UP,
    DeliveryStatus.PICKED_UP: DeliveryStatus.IN_TRANSIT,
    DeliveryStatus.IN_TRANSIT: DeliveryStatus.DELIVERED,
}


def require_dispatcher(actor: User) -> None:
    if actor.role not in (UserRole.ADMIN, UserRole.RESTAURANT_OWNER, UserRole.STAFF):
        raise HTTPException(403, detail="Restaurant management or administrator access required")


def visible_deliveries_query(db: Session, actor: User):
    query = select(Delivery)
    if actor.role == UserRole.DRIVER:
        return query.where(Delivery.driver_id == own_driver(db, actor).id)
    orders = visible_orders_query(actor).with_only_columns(Order.id)
    return query.where(Delivery.order_id.in_(orders))


def accessible_delivery(db: Session, actor: User, delivery_id: UUID) -> Delivery:
    delivery = db.scalar(visible_deliveries_query(db, actor).where(Delivery.id == delivery_id))
    if delivery is None:
        raise HTTPException(404, detail="Delivery not found")
    return delivery


def lock_delivery_order(db: Session, delivery: Delivery) -> Order:
    # Same lock order as direct order transitions and delivery creation.
    order = db.scalar(select(Order).where(Order.id == delivery.order_id)
                      .with_for_update().execution_options(populate_existing=True))
    if order is None:
        raise HTTPException(404, detail="Order not found")
    db.execute(select(Delivery.id).where(Delivery.id == delivery.id).with_for_update()).first()
    db.refresh(delivery)
    return order


def append_history(db: Session, delivery: Delivery, actor: User,
                   previous: DeliveryStatus | None, note: str | None) -> None:
    db.add(DeliveryStatusHistory(delivery_id=delivery.id, from_status=previous,
                                to_status=delivery.status, changed_by_user_id=actor.id,
                                note=note, created_at=datetime.now(timezone.utc)))


def create_delivery(db: Session, actor: User, order_id: UUID, note: str | None) -> Delivery:
    require_dispatcher(actor)
    order = accessible_order(db, actor, order_id)
    try:
        db.execute(select(Order.id).where(Order.id == order.id).with_for_update()).first()
        db.refresh(order)
        if order.status != OrderStatus.READY_FOR_PICKUP:
            raise HTTPException(409, detail="Order must be READY_FOR_PICKUP")
        if db.scalar(select(Delivery.id).where(Delivery.order_id == order.id)) is not None:
            raise HTTPException(409, detail="Order already has a Delivery")
        delivery = Delivery(order_id=order.id, status=DeliveryStatus.UNASSIGNED)
        db.add(delivery)
        db.flush()
        append_history(db, delivery, actor, None, note)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="Delivery creation conflict") from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(delivery)
    return delivery


def assign_driver(db: Session, actor: User, delivery_id: UUID, driver_id: UUID) -> Delivery:
    require_dispatcher(actor)
    delivery = accessible_delivery(db, actor, delivery_id)
    try:
        order = lock_delivery_order(db, delivery)
        if (order.status != OrderStatus.READY_FOR_PICKUP or
                delivery.status not in (DeliveryStatus.UNASSIGNED, DeliveryStatus.ASSIGNED)):
            raise HTTPException(409, detail="Assignment is allowed only before pickup of a ready order")
        if delivery.driver_id == driver_id:
            raise HTTPException(409, detail="Driver is already assigned")
        driver = db.scalar(select(Driver).where(Driver.id == driver_id).with_for_update()
                           .execution_options(populate_existing=True))
        if driver is None:
            raise HTTPException(404, detail="Driver not found")
        user = db.get(User, driver.user_id, populate_existing=True)
        if user is None or user.role != UserRole.DRIVER or not user.is_active or not driver.is_available:
            raise HTTPException(409, detail="Driver is not eligible or available")
        if active_delivery(db, driver.id) is not None:
            raise HTTPException(409, detail="Driver already has an active delivery")
        previous, old_driver = delivery.status, delivery.driver_id
        delivery.driver_id = driver.id
        delivery.status = DeliveryStatus.ASSIGNED
        delivery.assigned_at = datetime.now(timezone.utc)
        note = (f"Reassigned from driver {old_driver} to driver {driver.id}" if old_driver
                else f"Assigned driver {driver.id}")
        append_history(db, delivery, actor, previous, note)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="Delivery assignment conflict") from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(delivery)
    return delivery


def transition_delivery(db: Session, actor: User, delivery_id: UUID,
                        target: DeliveryStatus, note: str | None) -> Delivery:
    if actor.role not in (UserRole.ADMIN, UserRole.DRIVER):
        raise HTTPException(403, detail="Only ADMIN or the assigned DRIVER may progress delivery")
    delivery = accessible_delivery(db, actor, delivery_id)
    try:
        order = lock_delivery_order(db, delivery)
        # Recheck assignment after acquiring locks: dispatch may have reassigned it.
        if actor.role == UserRole.DRIVER and delivery.driver_id != own_driver(db, actor).id:
            raise HTTPException(404, detail="Delivery not found")
        if NEXT_STATUS.get(delivery.status) != target:
            raise InvalidTransitionError("Invalid delivery status transition")
        if delivery.driver_id is None:
            raise HTTPException(409, detail="Delivery has no assigned driver")
        expected_order = (OrderStatus.READY_FOR_PICKUP if delivery.status == DeliveryStatus.ASSIGNED
                          else OrderStatus.OUT_FOR_DELIVERY)
        if order.status != expected_order:
            raise HTTPException(409, detail="Order and Delivery statuses are inconsistent")
        previous = delivery.status
        delivery.status = target
        now = datetime.now(timezone.utc)
        if target == DeliveryStatus.PICKED_UP:
            delivery.picked_up_at = now
            apply_order_transition(db, actor, order, OrderStatus.OUT_FOR_DELIVERY,
                                   f"Delivery {delivery.id} picked up")
        elif target == DeliveryStatus.DELIVERED:
            delivery.delivered_at = now
            apply_order_transition(db, actor, order, OrderStatus.DELIVERED,
                                   f"Delivery {delivery.id} delivered")
        append_history(db, delivery, actor, previous, note)
        db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="Delivery transition conflict") from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(delivery)
    return delivery


def delivery_history(db: Session, actor: User, delivery_id: UUID):
    accessible_delivery(db, actor, delivery_id)
    return db.scalars(select(DeliveryStatusHistory).where(DeliveryStatusHistory.delivery_id == delivery_id)
                      .order_by(DeliveryStatusHistory.created_at, DeliveryStatusHistory.id)).all()
