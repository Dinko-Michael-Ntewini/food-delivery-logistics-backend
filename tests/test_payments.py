"""Stage 7 payment and refund lifecycle, authorization, and rollback tests."""

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.core.enums import PaymentStatus, RefundStatus, UserRole
from app.core.security import hash_password
from app.models.identity import User
from app.models.ordering import CartItem, Order, OrderItem, OrderStatusHistory
from app.models.payment import Payment, Refund
from app.models.restaurant import RestaurantStaff
from test_orders import auth, checkout, fill_cart, order_setup  # shared Stage 6 fixture and API helpers


def make_payment(client, data, db_session, *, with_variant=True):
    fill_cart(client, data, with_variant=with_variant)
    result = checkout(client, data)
    assert result.status_code == 201, result.text
    order = result.json()
    payment = db_session.scalar(select(Payment).where(Payment.order_id == UUID(order["id"])))
    assert payment is not None
    return order, payment


def refund_request(client, payment, actor, amount, reason="Customer request"):
    return client.post(f"/payments/{payment.id}/refunds",
                       json={"amount": amount, "reason": reason}, headers=auth(actor))


def test_payment_retrieval_and_restaurant_scope(client, order_setup, db_session):
    data = order_setup
    order, payment = make_payment(client, data, db_session)
    path = f"/payments/{payment.id}"
    order_path = f"/orders/{order['id']}/payments"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=auth(data["customer"])).status_code == 200
    assert client.get(order_path, headers=auth(data["customer"])).status_code == 200
    assert len(client.get(order_path, headers=auth(data["customer"])).json()) == 1
    assert client.get(path, headers=auth(data["owner"])).status_code == 200
    assert client.get(path, headers=auth(data["staff"])).status_code == 200
    assert client.get(path, headers=auth(data["admin"])).status_code == 200
    for name in ("other_customer", "other_owner", "other_staff", "wrong_branch_staff"):
        assert client.get(path, headers=auth(data[name])).status_code == 404
        assert client.get(order_path, headers=auth(data[name])).status_code == 404
    assert client.get(path, headers=auth(data["driver"])).status_code == 403
    assert client.get("/payments/not-a-uuid", headers=auth(data["customer"])).status_code == 422
    assert client.get(f"/payments/{UUID(int=1)}", headers=auth(data["admin"])).status_code == 404
    body = client.get(path, headers=auth(data["customer"])).json()
    assert body["status"] == "PENDING"
    assert Decimal(body["amount"]) == Decimal(order["total_amount"])
    assert Decimal(body["total_refunded"]) == Decimal("0.00")
    assert body["method"] == "CASH_ON_DELIVERY"


def test_confirmation_validates_amount_and_is_admin_only(client, order_setup, db_session):
    data = order_setup
    order, payment = make_payment(client, data, db_session)
    path = f"/payments/{payment.id}/confirm"
    assert client.post(path).status_code == 401
    for name in ("customer", "owner", "staff", "driver"):
        assert client.post(path, headers=auth(data[name])).status_code == 403
    payment.amount = Decimal("0.01")
    db_session.commit()
    assert client.post(path, headers=auth(data["admin"])).status_code == 409
    payment.amount = Decimal(order["total_amount"])
    db_session.commit()
    result = client.post(path, headers=auth(data["admin"]))
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["status"] == "CAPTURED"
    assert body["paid_at"] is not None
    assert body["reference"].startswith("SIM-")
    assert Decimal(body["amount"]) == Decimal(order["total_amount"])
    assert client.post(path, headers=auth(data["admin"])).status_code == 409
    assert client.post(f"/payments/{payment.id}/fail", headers=auth(data["admin"])).status_code == 409
    assert db_session.scalar(select(func.count()).select_from(Payment).where(Payment.order_id == UUID(order["id"]))) == 1


def test_pending_failure_is_terminal_and_preserves_order(client, order_setup, db_session):
    data = order_setup
    order, payment = make_payment(client, data, db_session)
    before_items = db_session.scalar(select(func.count()).select_from(OrderItem))
    before_history = db_session.scalar(select(func.count()).select_from(OrderStatusHistory))
    fail_path = f"/payments/{payment.id}/fail"
    assert client.post(fail_path, headers=auth(data["customer"])).status_code == 403
    result = client.post(fail_path, headers=auth(data["admin"]))
    assert result.status_code == 200 and result.json()["status"] == "FAILED"
    assert result.json()["paid_at"] is None
    assert client.post(fail_path, headers=auth(data["admin"])).status_code == 409
    assert client.post(f"/payments/{payment.id}/confirm", headers=auth(data["admin"])).status_code == 409
    assert refund_request(client, payment, data["admin"], "1.00").status_code == 409
    assert db_session.get(Order, UUID(order["id"])) is not None
    assert db_session.scalar(select(func.count()).select_from(OrderItem)) == before_items
    assert db_session.scalar(select(func.count()).select_from(OrderStatusHistory)) == before_history
    assert db_session.scalar(select(func.count()).select_from(CartItem)) == 0


def test_refund_preconditions_and_validation(client, order_setup, db_session):
    data = order_setup
    order, payment = make_payment(client, data, db_session)
    assert refund_request(client, payment, data["admin"], "1.00").status_code == 409
    assert client.post(f"/payments/{UUID(int=1)}/refunds", json={"amount": "1.00", "reason": "Test"},
                       headers=auth(data["admin"])).status_code == 404
    assert client.post(f"/payments/{payment.id}/refunds", json={"amount": "1.00", "reason": "Test"}).status_code == 401
    for name in ("customer", "owner", "staff", "driver"):
        assert refund_request(client, payment, data[name], "1.00").status_code == 403
    assert client.post(f"/payments/{payment.id}/confirm", headers=auth(data["admin"])).status_code == 200
    payment.amount = Decimal("0.01")
    db_session.commit()
    assert refund_request(client, payment, data["admin"], "0.01").status_code == 409
    payment.amount = Decimal(order["total_amount"])
    db_session.commit()
    for amount in ("0", "-1", "1.001", "100000000000.00"):
        assert refund_request(client, payment, data["admin"], amount).status_code == 422
    assert refund_request(client, payment, data["admin"], "1.00", reason="   ").status_code == 422
    assert client.post(f"/payments/{payment.id}/refunds",
                       json={"amount": "1.00", "reason": "Test", "payment_id": str(payment.id)},
                       headers=auth(data["admin"])).status_code == 422
    assert refund_request(client, payment, data["admin"], "999.99").status_code == 409


def test_multiple_partial_refunds_exact_full_and_financial_invariants(client, order_setup, db_session):
    data = order_setup
    data["product"].base_price = Decimal("50.00")
    db_session.commit()
    order, payment = make_payment(client, data, db_session, with_variant=False)
    assert Decimal(order["total_amount"]) == Decimal("100.00")
    captured = client.post(f"/payments/{payment.id}/confirm", headers=auth(data["admin"]))
    assert captured.status_code == 200
    original_items = client.get(f"/orders/{order['id']}", headers=auth(data["customer"])).json()["items"]
    original_history = db_session.scalar(select(func.count()).select_from(OrderStatusHistory))
    first = refund_request(client, payment, data["admin"], "30.00", "First partial")
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "SUCCEEDED"
    second = refund_request(client, payment, data["admin"], "20.00", "Second partial")
    assert second.status_code == 201, second.text
    intermediate = client.get(f"/payments/{payment.id}", headers=auth(data["customer"])).json()
    assert intermediate["status"] == "CAPTURED"
    assert Decimal(intermediate["total_refunded"]) == Decimal("50.00")
    assert Decimal(intermediate["remaining_refundable"]) == Decimal("50.00")
    assert refund_request(client, payment, data["admin"], "50.01").status_code == 409
    final = refund_request(client, payment, data["admin"], "50.00", "Final remainder")
    assert final.status_code == 201
    complete = client.get(f"/payments/{payment.id}", headers=auth(data["customer"])).json()
    assert complete["status"] == "REFUNDED"
    assert Decimal(complete["total_refunded"]) == Decimal("100.00")
    assert Decimal(complete["remaining_refundable"]) == Decimal("0.00")
    assert refund_request(client, payment, data["admin"], "0.01").status_code == 409
    rows = client.get(f"/payments/{payment.id}/refunds", headers=auth(data["customer"]))
    assert rows.status_code == 200 and len(rows.json()) == 3
    assert client.get(f"/refunds/{first.json()['id']}", headers=auth(data["customer"])).status_code == 200
    assert client.get(f"/refunds/{first.json()['id']}", headers=auth(data["owner"])).status_code == 200
    for name in ("other_customer", "other_owner", "other_staff", "wrong_branch_staff"):
        assert client.get(f"/refunds/{first.json()['id']}", headers=auth(data[name])).status_code == 404
        assert client.get(f"/payments/{payment.id}/refunds", headers=auth(data[name])).status_code == 404
    assert db_session.scalar(select(func.count()).select_from(OrderStatusHistory)) == original_history
    assert client.get(f"/orders/{order['id']}", headers=auth(data["customer"])).json()["items"] == original_items
    assert db_session.get(Order, UUID(order["id"])) is not None
    assert db_session.scalar(select(func.count()).select_from(CartItem)) == 0


def test_direct_full_refund_and_inactive_membership(client, order_setup, db_session):
    data = order_setup
    _, payment = make_payment(client, data, db_session)
    assert client.post(f"/payments/{payment.id}/confirm", headers=auth(data["admin"])).status_code == 200
    owner_membership = db_session.scalar(select(RestaurantStaff).where(RestaurantStaff.user_id == data["owner"].id))
    owner_membership.is_active = False
    db_session.commit()
    assert client.get(f"/payments/{payment.id}", headers=auth(data["owner"])).status_code == 404
    full = refund_request(client, payment, data["admin"], str(payment.amount))
    assert full.status_code == 201
    assert db_session.get(Payment, payment.id).status == PaymentStatus.REFUNDED
    assert db_session.get(Refund, UUID(full.json()["id"])).status == RefundStatus.SUCCEEDED


def test_refund_failure_rolls_back_balance_and_status(client, order_setup, db_session, monkeypatch):
    data = order_setup
    _, payment = make_payment(client, data, db_session)
    assert client.post(f"/payments/{payment.id}/confirm", headers=auth(data["admin"])).status_code == 200
    before = client.get(f"/payments/{payment.id}", headers=auth(data["customer"])).json()
    with monkeypatch.context() as patch:
        patch.setattr(db_session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("forced refund commit failure")))
        with pytest.raises(RuntimeError, match="forced refund commit failure"):
            refund_request(client, payment, data["admin"], str(payment.amount))
    assert db_session.scalar(select(func.count()).select_from(Refund)) == 0
    assert db_session.get(Payment, payment.id).status == PaymentStatus.CAPTURED
    after = client.get(f"/payments/{payment.id}", headers=auth(data["customer"])).json()
    assert after["total_refunded"] == before["total_refunded"]
    assert after["remaining_refundable"] == before["remaining_refundable"]


def test_stage7_openapi_contract(client):
    document = client.get("/openapi.json").json()
    required = {
        ("/payments/{payment_id}", "get", "Payments"),
        ("/orders/{order_id}/payments", "get", "Payments"),
        ("/payments/{payment_id}/confirm", "post", "Payments"),
        ("/payments/{payment_id}/fail", "post", "Payments"),
        ("/payments/{payment_id}/refunds", "post", "Refunds"),
        ("/payments/{payment_id}/refunds", "get", "Refunds"),
        ("/refunds/{refund_id}", "get", "Refunds"),
    }
    for path, method, tag in required:
        operation = document["paths"][path][method]
        assert operation["tags"] == [tag]
        assert operation["security"] == [{"HTTPBearer": []}]
    assert "patch" not in document["paths"]["/payments/{payment_id}"]
    ids = [operation["operationId"] for paths in document["paths"].values()
           for method, operation in paths.items() if method in {"get", "post", "patch", "delete"}]
    assert len(ids) == len(set(ids))
    schemas = str(document["components"]["schemas"])
    assert "password_hash" not in schemas and "card_number" not in schemas


def test_stage7_api_driven_end_to_end_flow(client, order_setup, db_session):
    data = order_setup
    data["product"].base_price = Decimal("50.00")
    db_session.commit()
    registered = client.post("/auth/register", json={"email": "stage7-flow@example.com",
                                                   "password": "password123", "full_name": "Stage Seven"})
    assert registered.status_code == 201
    login = client.post("/auth/login", json={"email": "stage7-flow@example.com",
                                               "password": "password123"})
    assert login.status_code == 200
    customer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    address = client.post("/customers/me/addresses", json={"label": "Home", "recipient_name": "Stage Seven",
                                                           "recipient_phone": "123", "line1": "7 Road", "city": "Accra"},
                          headers=customer_headers)
    assert address.status_code == 201
    cart = client.post("/cart/items", json={"product_id": str(data["product"].id),
                                            "branch_id": str(data["branch"].id), "quantity": 2},
                       headers=customer_headers)
    assert cart.status_code == 201
    placed = client.post("/orders/checkout", json={"address_id": address.json()["id"],
                                                    "payment_method": "MOBILE_MONEY"},
                         headers=customer_headers)
    assert placed.status_code == 201
    order = placed.json()
    assert Decimal(order["total_amount"]) == Decimal("100.00")
    original_items = order["items"]
    original_history = order["status_history"]
    payments = client.get(f"/orders/{order['id']}/payments", headers=customer_headers)
    assert payments.status_code == 200 and len(payments.json()) == 1
    payment = payments.json()[0]
    assert payment["status"] == "PENDING"
    assert payment["method"] == "MOBILE_MONEY"
    payment_id = payment["id"]
    confirmed = client.post(f"/payments/{payment_id}/confirm", headers=auth(data["admin"]))
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "CAPTURED"
    assert client.get(f"/payments/{payment_id}", headers=customer_headers).json()["status"] == "CAPTURED"

    def create(amount):
        return client.post(f"/payments/{payment_id}/refunds",
                           json={"amount": amount, "reason": "Stage 7 flow"},
                           headers=auth(data["admin"]))

    first = create("30.00")
    second = create("20.00")
    assert first.status_code == 201 and second.status_code == 201
    half = client.get(f"/payments/{payment_id}", headers=customer_headers).json()
    assert Decimal(half["total_refunded"]) == Decimal("50.00")
    assert Decimal(half["remaining_refundable"]) == Decimal("50.00")
    assert create("50.01").status_code == 409
    final = create("50.00")
    assert final.status_code == 201
    full = client.get(f"/payments/{payment_id}", headers=customer_headers).json()
    assert full["status"] == "REFUNDED"
    assert Decimal(full["total_refunded"]) == Decimal("100.00")
    assert Decimal(full["remaining_refundable"]) == Decimal("0.00")
    assert create("0.01").status_code == 409
    refunds = client.get(f"/payments/{payment_id}/refunds", headers=customer_headers)
    assert refunds.status_code == 200 and len(refunds.json()) == 3
    assert client.get(f"/refunds/{first.json()['id']}", headers=customer_headers).status_code == 200
    assert client.get(f"/payments/{payment_id}", headers=auth(data["other_customer"])).status_code == 404
    assert client.get(f"/refunds/{first.json()['id']}", headers=auth(data["other_customer"])).status_code == 404
    historic = client.get(f"/orders/{order['id']}", headers=customer_headers).json()
    assert historic["items"] == original_items
    assert historic["status_history"] == original_history
    assert client.get("/cart", headers=customer_headers).json()["items"] == []
