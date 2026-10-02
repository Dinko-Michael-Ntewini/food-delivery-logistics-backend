"""Read-only financial visibility and administrator-controlled actions."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.identity import User
from app.schemas.payment import PaymentCreate, PaymentResponse, RefundCreate, RefundResponse
from app.services.payments import (
    checkout_payment, confirm_payment, create_refund, fail_payment, list_order_payments,
    list_refunds, payment_for_actor, payment_response, refund_for_actor,
)

router = APIRouter()
DB = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(get_current_active_user)]


@router.post("/payments", response_model=PaymentResponse, tags=["Payments"],
             description="Idempotently return the Payment created by checkout. Never creates a second Payment.")
def post_payment(payload: PaymentCreate, db: DB, actor: Actor) -> PaymentResponse:
    return checkout_payment(db, actor, payload.order_id)


@router.get("/payments/{payment_id}", response_model=PaymentResponse, tags=["Payments"])
def get_payment(payment_id: UUID, db: DB, actor: Actor) -> PaymentResponse:
    return payment_response(db, payment_for_actor(db, actor, payment_id))


@router.get("/orders/{order_id}/payments", response_model=list[PaymentResponse], tags=["Payments"])
def get_order_payments(order_id: UUID, db: DB, actor: Actor) -> list[PaymentResponse]:
    return list_order_payments(db, actor, order_id)


@router.post("/payments/{payment_id}/confirm", response_model=PaymentResponse, tags=["Payments"])
def post_payment_confirm(payment_id: UUID, db: DB, actor: Actor) -> PaymentResponse:
    return confirm_payment(db, actor, payment_id)


@router.post("/payments/{payment_id}/fail", response_model=PaymentResponse, tags=["Payments"])
def post_payment_fail(payment_id: UUID, db: DB, actor: Actor) -> PaymentResponse:
    return fail_payment(db, actor, payment_id)


@router.post("/payments/{payment_id}/refunds", response_model=RefundResponse,
             status_code=status.HTTP_201_CREATED, tags=["Refunds"])
def post_refund(payment_id: UUID, payload: RefundCreate, db: DB, actor: Actor) -> RefundResponse:
    return create_refund(db, actor, payment_id, payload)


@router.get("/payments/{payment_id}/refunds", response_model=list[RefundResponse], tags=["Refunds"])
def get_payment_refunds(payment_id: UUID, db: DB, actor: Actor) -> list[RefundResponse]:
    return list_refunds(db, actor, payment_id)


@router.get("/refunds/{refund_id}", response_model=RefundResponse, tags=["Refunds"])
def get_refund(refund_id: UUID, db: DB, actor: Actor) -> RefundResponse:
    return refund_for_actor(db, actor, refund_id)
