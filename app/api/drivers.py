from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from app.core.pagination import sorted_query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.delivery import Delivery, Driver
from app.models.identity import User
from app.schemas.delivery import DeliveryResponse
from app.schemas.driver import DriverCreate, DriverResponse, DriverUpdate
from app.services import drivers
from app.services.deliveries import visible_deliveries_query

router = APIRouter(prefix="/drivers", tags=["Drivers"])
DB = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(get_current_active_user)]


@router.get("/me", response_model=DriverResponse)
def get_my_driver(db: DB, actor: Actor):
    return drivers.own_driver(db, actor)


@router.get("/me/deliveries", response_model=list[DeliveryResponse])
def get_my_deliveries(db: DB, actor: Actor):
    drivers.own_driver(db, actor)
    return db.scalars(visible_deliveries_query(db, actor).order_by(Delivery.created_at, Delivery.id)).all()


@router.get("", response_model=list[DriverResponse])
def list_drivers(db: DB, actor: Actor, is_available: bool | None = None,
                 sort: str = Query("created_at", pattern="^-?(created_at|updated_at|vehicle_type)$")):
    drivers.require_admin(actor)
    query = select(Driver)
    if is_available is not None:
        query = query.where(Driver.is_available == is_available)
    return db.scalars(sorted_query(query, sort, {"created_at": Driver.created_at,
                      "updated_at": Driver.updated_at, "vehicle_type": Driver.vehicle_type}, Driver.id)).all()


@router.post("", response_model=DriverResponse, status_code=201)
def post_driver(payload: DriverCreate, db: DB, actor: Actor):
    return drivers.create_driver(db, actor, payload)


@router.get("/{driver_id}", response_model=DriverResponse)
def get_driver(driver_id: UUID, db: DB, actor: Actor):
    return drivers.get_driver(db, actor, driver_id)


@router.patch("/{driver_id}", response_model=DriverResponse)
def patch_driver(driver_id: UUID, payload: DriverUpdate, db: DB, actor: Actor):
    return drivers.update_driver(db, actor, driver_id, payload)
