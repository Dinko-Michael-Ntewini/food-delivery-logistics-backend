"""Driver profiles and eligibility; linked users are never changed by profile updates."""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import DeliveryStatus, UserRole
from app.models.delivery import Delivery, Driver
from app.models.identity import User
from app.schemas.driver import DriverCreate, DriverUpdate

ACTIVE_STATUSES = (DeliveryStatus.ASSIGNED, DeliveryStatus.PICKED_UP, DeliveryStatus.IN_TRANSIT)


def require_admin(actor: User) -> None:
    if actor.role != UserRole.ADMIN:
        raise HTTPException(403, detail="Administrator access required")


def own_driver(db: Session, actor: User) -> Driver:
    if actor.role != UserRole.DRIVER or not actor.is_active:
        raise HTTPException(403, detail="Active DRIVER access required")
    driver = db.scalar(select(Driver).where(Driver.user_id == actor.id))
    if driver is None:
        raise HTTPException(404, detail="Driver profile not found")
    return driver


def active_delivery(db: Session, driver_id: UUID):
    return db.scalar(select(Delivery.id).where(Delivery.driver_id == driver_id,
                                              Delivery.status.in_(ACTIVE_STATUSES)).limit(1))


def create_driver(db: Session, actor: User, payload: DriverCreate) -> Driver:
    require_admin(actor)
    user = db.get(User, payload.user_id)
    if user is None:
        raise HTTPException(404, detail="User not found")
    if user.role != UserRole.DRIVER or not user.is_active:
        raise HTTPException(409, detail="Profile requires an active DRIVER user")
    driver = Driver(**payload.model_dump())
    try:
        db.add(driver)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="Driver profile or vehicle identifier already exists") from exc
    db.refresh(driver)
    return driver


def get_driver(db: Session, actor: User, driver_id: UUID) -> Driver:
    if actor.role != UserRole.ADMIN:
        driver = own_driver(db, actor)
        if driver.id != driver_id:
            raise HTTPException(404, detail="Driver not found")
        return driver
    driver = db.get(Driver, driver_id)
    if driver is None:
        raise HTTPException(404, detail="Driver not found")
    return driver


def update_driver(db: Session, actor: User, driver_id: UUID, payload: DriverUpdate) -> Driver:
    driver = get_driver(db, actor, driver_id)
    try:
        db.execute(select(Driver.id).where(Driver.id == driver.id).with_for_update()).first()
        db.refresh(driver)
        if payload.is_available is False and active_delivery(db, driver.id):
            raise HTTPException(409, detail="Cannot become unavailable during an active delivery")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(driver, key, value)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="Vehicle identifier already exists") from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(driver)
    return driver
