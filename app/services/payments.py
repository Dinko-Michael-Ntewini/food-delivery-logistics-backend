"""Manual payment capture/failure and transaction-safe internal refunds."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import PaymentStatus, RefundStatus, UserRole
from app.core.exceptions import InvalidTransitionError
from app.models.identity import User
from app.models.ordering import Order
from app.models.payment import Payment, Refund
from app.schemas.payment import PaymentResponse, RefundCreate, RefundResponse
from app.services.orders import accessible_order


ZERO = Decimal("0.00")


def require_admin(actor: User) -> None:
    if actor.role != UserRole.ADMIN:
        raise HTTPException(403, detail="Financial state changes require administrator access")


def payment_for_actor(db: Session, actor: User, payment_id: UUID) -> Payment:
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(404, detail="Payment not found")
    accessible_order(db, actor, payment.order_id)
    return payment


def successful_refund_total(db: Session, payment_id: UUID) -> Decimal:
    result = db.scalar(select(func.sum(Refund.amount)).where(
        Refund.payment_id == payment_id, Refund.status == RefundStatus.SUCCEEDED))
    return result if result is not None else ZERO


def refund_balances(db: Session, payment: Payment) -> tuple[Decimal, Decimal]:
    refunded = successful_refund_total(db, payment.id)
    remaining = payment.amount - refunded
    if remaining < ZERO:
        raise HTTPException(409, detail="Refund records exceed the payment amount")
    return refunded, remaining


def payment_response(db: Session, payment: Payment) -> PaymentResponse:
    refunded, remaining = refund_balances(db, payment)
    return PaymentResponse(
        id=payment.id, order_id=payment.order_id, amount=payment.amount,
        currency=payment.currency, method=payment.provider, status=payment.status,
        reference=payment.provider_reference, paid_at=payment.paid_at,
        created_at=payment.created_at, updated_at=payment.updated_at,
        total_refunded=refunded, remaining_refundable=remaining,
    )


def refund_response(refund: Refund) -> RefundResponse:
    return RefundResponse(
        id=refund.id, payment_id=refund.payment_id, amount=refund.amount,
        reason=refund.reason, status=refund.status,
        reference=refund.provider_reference,
        created_at=refund.created_at, updated_at=refund.updated_at,
    )


def list_order_payments(db: Session, actor: User, order_id: UUID) -> list[PaymentResponse]:
    accessible_order(db, actor, order_id)
    payments = db.scalars(select(Payment).where(Payment.order_id == order_id)
                          .order_by(Payment.created_at, Payment.id)).all()
    return [payment_response(db, payment) for payment in payments]


def checkout_payment(db: Session, actor: User, order_id: UUID) -> PaymentResponse:
    if actor.role not in (UserRole.ADMIN, UserRole.CUSTOMER):
        raise HTTPException(403, detail="Customer or administrator access required")
    payments = list_order_payments(db, actor, order_id)
    if not payments:
        raise HTTPException(409, detail="Order is missing its checkout Payment")
    return payments[0]


def confirm_payment(db: Session, actor: User, payment_id: UUID) -> PaymentResponse:
    require_admin(actor)
    try:
        payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
        if payment is None:
            raise HTTPException(404, detail="Payment not found")
        if payment.status != PaymentStatus.PENDING:
            raise InvalidTransitionError("Only a pending payment may be confirmed")
        order = db.get(Order, payment.order_id)
        if order is None:
            raise HTTPException(409, detail="Payment order no longer exists")
        if payment.amount != order.total_amount:
            raise HTTPException(409, detail="Payment amount does not match the order total")
        payment.status = PaymentStatus.CAPTURED
        payment.paid_at = datetime.now(timezone.utc)
        if payment.provider_reference is None:
            payment.provider_reference = f"SIM-{uuid4().hex.upper()}"
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="Payment confirmation conflicted with current data") from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(payment)
    return payment_response(db, payment)


def fail_payment(db: Session, actor: User, payment_id: UUID) -> PaymentResponse:
    require_admin(actor)
    try:
        payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
        if payment is None:
            raise HTTPException(404, detail="Payment not found")
        if payment.status != PaymentStatus.PENDING:
            raise InvalidTransitionError("Only a pending payment may be failed")
        payment.status = PaymentStatus.FAILED
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="Payment failure conflicted with current data") from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(payment)
    return payment_response(db, payment)


def create_refund(db: Session, actor: User, payment_id: UUID,
                  payload: RefundCreate) -> RefundResponse:
    require_admin(actor)
    try:
        payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
        if payment is None:
            raise HTTPException(404, detail="Payment not found")
        if payment.status != PaymentStatus.CAPTURED:
            raise HTTPException(409, detail="Only a captured payment may be refunded")
        order = db.get(Order, payment.order_id)
        if order is None or payment.amount != order.total_amount:
            raise HTTPException(409, detail="Payment amount does not match its order")
        _, remaining = refund_balances(db, payment)
        if payload.amount > remaining:
            raise HTTPException(409, detail="Refund exceeds the remaining payment balance")
        refund = Refund(
            payment_id=payment.id, amount=payload.amount, reason=payload.reason,
            status=RefundStatus.SUCCEEDED,
            provider_reference=f"SIM-R-{uuid4().hex.upper()}",
        )
        db.add(refund)
        if payload.amount == remaining:
            payment.status = PaymentStatus.REFUNDED
        db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="Refund conflicted with current data") from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(refund)
    return refund_response(refund)


def list_refunds(db: Session, actor: User, payment_id: UUID) -> list[RefundResponse]:
    payment_for_actor(db, actor, payment_id)
    rows = db.scalars(select(Refund).where(Refund.payment_id == payment_id)
                      .order_by(Refund.created_at, Refund.id)).all()
    return [refund_response(row) for row in rows]


def refund_for_actor(db: Session, actor: User, refund_id: UUID) -> RefundResponse:
    refund = db.get(Refund, refund_id)
    if refund is None:
        raise HTTPException(404, detail="Refund not found")
    payment_for_actor(db, actor, refund.payment_id)
    return refund_response(refund)
