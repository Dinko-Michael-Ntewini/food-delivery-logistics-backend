"""Stage 6 checkout, order reading, and status transitions."""

from typing import Annotated, Literal
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.enums import OrderStatus
from app.core.pagination import PageNumber, PageSize, resolve_list_aliases
from app.db.session import get_db
from app.models.identity import User
from app.schemas.order import CheckoutRequest, OrderOut, OrderPage, OrderStatusHistoryOut, OrderStatusUpdate
from app.services.orders import accessible_order, checkout, list_orders, order_response, transition_order

router = APIRouter(prefix="/orders", tags=["Orders"])
DB = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(get_current_active_user)]


@router.post("/checkout", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def checkout_order(payload: CheckoutRequest, db: DB, actor: Actor) -> OrderOut:
    return checkout(db, actor, payload)


@router.get("", response_model=OrderPage)
def get_orders(request: Request, db: DB, actor: Actor, page: PageNumber = 1, page_size: PageSize = 20,
               status_filter: OrderStatus | None = Query(None, alias="status"),
               restaurant_id: UUID | None = None, branch_id: UUID | None = None,
               search: str | None = Query(None, max_length=100, description="Order number contains text"),
               customer_id: UUID | None = Query(None, description="ADMIN only; CustomerProfile ID"),
               date_from: datetime | None = Query(None, description="Inclusive placed_at lower bound; naive timestamps are UTC"),
               date_to: datetime | None = Query(None, description="Inclusive placed_at upper bound; naive timestamps are UTC"),
               sort: str = Query("-placed_at", pattern="^-?(placed_at|created_at|updated_at|total|status)$"),
               limit: int | None = Query(None, ge=1, le=100),
               sort_by: str | None = Query(None, pattern="^(placed_at|created_at|updated_at|total|status)$"),
               order: Literal["asc", "desc"] | None = None) -> OrderPage:
    page_size, sort = resolve_list_aliases(request, page_size, sort, limit=limit, sort_by=sort_by, order=order)
    return list_orders(db, actor, page, page_size, status_filter, restaurant_id=restaurant_id,
                       branch_id=branch_id, customer_id=customer_id, date_from=date_from,
                       date_to=date_to, sort=sort, search=search)


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: UUID, db: DB, actor: Actor) -> OrderOut:
    return order_response(db, accessible_order(db, actor, order_id))


@router.get("/{order_id}/status-history", response_model=list[OrderStatusHistoryOut])
def get_order_history(order_id: UUID, db: DB, actor: Actor) -> list[OrderStatusHistoryOut]:
    return order_response(db, accessible_order(db, actor, order_id)).status_history


@router.patch("/{order_id}/status", response_model=OrderOut)
def patch_order_status(order_id: UUID, payload: OrderStatusUpdate,
                       db: DB, actor: Actor) -> OrderOut:
    return transition_order(db, actor, order_id, payload.status, payload.reason)
