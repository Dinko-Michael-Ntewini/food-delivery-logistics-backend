from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from app.core.enums import DeliveryStatus
from app.core.pagination import sorted_query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.delivery import Delivery
from app.models.identity import User
from app.schemas.delivery import (
    DeliveryAssign, DeliveryCreate, DeliveryHistoryResponse, DeliveryResponse, DeliveryTransition,
)
from app.services import deliveries

router = APIRouter(tags=["Deliveries"])
DB = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(get_current_active_user)]


@router.post("/orders/{order_id}/delivery", response_model=DeliveryResponse, status_code=201)
def post_delivery(order_id: UUID, payload: DeliveryCreate, db: DB, actor: Actor):
    return deliveries.create_delivery(db, actor, order_id, payload.note)


@router.get("/deliveries", response_model=list[DeliveryResponse])
def list_deliveries(db: DB, actor: Actor,
                    status_filter: DeliveryStatus | None = Query(None, alias="status"),
                    driver_id: UUID | None = None, order_id: UUID | None = None,
                    sort: str = Query("created_at", pattern="^-?(created_at|updated_at|status)$")):
    query = deliveries.visible_deliveries_query(db, actor)
    if status_filter is not None:
        query = query.where(Delivery.status == status_filter)
    if driver_id is not None:
        query = query.where(Delivery.driver_id == driver_id)
    if order_id is not None:
        query = query.where(Delivery.order_id == order_id)
    return db.scalars(sorted_query(query, sort, {"created_at": Delivery.created_at,
                      "updated_at": Delivery.updated_at, "status": Delivery.status}, Delivery.id)).all()


@router.get("/deliveries/{delivery_id}", response_model=DeliveryResponse)
def get_delivery(delivery_id: UUID, db: DB, actor: Actor):
    return deliveries.accessible_delivery(db, actor, delivery_id)


@router.get("/deliveries/{delivery_id}/status-history", response_model=list[DeliveryHistoryResponse])
def get_delivery_history(delivery_id: UUID, db: DB, actor: Actor):
    return deliveries.delivery_history(db, actor, delivery_id)


@router.patch("/deliveries/{delivery_id}/assign", response_model=DeliveryResponse)
@router.post("/deliveries/{delivery_id}/assign-driver", response_model=DeliveryResponse)
def assign_delivery(delivery_id: UUID, payload: DeliveryAssign, db: DB, actor: Actor):
    return deliveries.assign_driver(db, actor, delivery_id, payload.driver_id)


@router.patch("/deliveries/{delivery_id}/status", response_model=DeliveryResponse)
def patch_delivery_status(delivery_id: UUID, payload: DeliveryTransition, db: DB, actor: Actor):
    return deliveries.transition_delivery(db, actor, delivery_id, payload.status, payload.note)
