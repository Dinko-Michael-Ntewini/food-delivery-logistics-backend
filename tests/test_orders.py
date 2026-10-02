"""Stage 6 checkout, snapshots, ownership, atomicity, and state-machine tests."""

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.core.enums import OrderStatus, PaymentStatus, RestaurantStaffRole, UserRole
from app.core.security import create_access_token, hash_password
from app.models.identity import Address, User
from app.models.ordering import Cart, CartItem, Order, OrderItem, OrderStatusHistory
from app.models.payment import Payment
from app.models.restaurant import (
    Category, Menu, Product, ProductVariant, Restaurant, RestaurantBranch, RestaurantStaff,
)


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def checkout_payload(address):
    return {"address_id": str(address.id), "payment_method": "CASH_ON_DELIVERY"}


@pytest.fixture()
def order_setup(db_session):
    def add_user(email, role):
        row = User(email=email, password_hash=hash_password("password123"),
                   full_name=email, role=role, is_active=True)
        db_session.add(row)
        db_session.flush()
        return row

    customer = add_user("order-customer@example.com", UserRole.CUSTOMER)
    other_customer = add_user("order-other-customer@example.com", UserRole.CUSTOMER)
    owner = add_user("order-owner@example.com", UserRole.RESTAURANT_OWNER)
    other_owner = add_user("order-other-owner@example.com", UserRole.RESTAURANT_OWNER)
    staff = add_user("order-staff@example.com", UserRole.STAFF)
    wrong_branch_staff = add_user("order-wrong-branch-staff@example.com", UserRole.STAFF)
    other_staff = add_user("order-other-staff@example.com", UserRole.STAFF)
    admin = add_user("order-admin@example.com", UserRole.ADMIN)
    driver = add_user("order-driver@example.com", UserRole.DRIVER)
    restaurant = Restaurant(name="Order Kitchen", slug="order-kitchen")
    foreign_restaurant = Restaurant(name="Foreign Kitchen", slug="foreign-kitchen")
    db_session.add_all([restaurant, foreign_restaurant])
    db_session.flush()
    branch = RestaurantBranch(restaurant_id=restaurant.id, name="Main", line1="1 Road", city="Accra")
    other_branch = RestaurantBranch(restaurant_id=restaurant.id, name="Alternate", line1="5 Road", city="Accra")
    foreign_branch = RestaurantBranch(restaurant_id=foreign_restaurant.id, name="Main", line1="2 Road", city="Accra")
    db_session.add_all([branch, other_branch, foreign_branch])
    db_session.flush()
    db_session.add_all([
        RestaurantStaff(restaurant_id=restaurant.id, user_id=owner.id, staff_role=RestaurantStaffRole.OWNER),
        RestaurantStaff(restaurant_id=foreign_restaurant.id, user_id=other_owner.id, staff_role=RestaurantStaffRole.OWNER),
        RestaurantStaff(restaurant_id=restaurant.id, branch_id=branch.id, user_id=staff.id, staff_role=RestaurantStaffRole.STAFF),
        RestaurantStaff(restaurant_id=restaurant.id, branch_id=other_branch.id, user_id=wrong_branch_staff.id, staff_role=RestaurantStaffRole.STAFF),
        RestaurantStaff(restaurant_id=foreign_restaurant.id, branch_id=foreign_branch.id, user_id=other_staff.id, staff_role=RestaurantStaffRole.STAFF),
    ])
    menu = Menu(restaurant_id=restaurant.id, name="Dinner")
    foreign_menu = Menu(restaurant_id=foreign_restaurant.id, name="Dinner")
    db_session.add_all([menu, foreign_menu])
    db_session.flush()
    category = Category(menu_id=menu.id, name="Mains")
    foreign_category = Category(menu_id=foreign_menu.id, name="Mains")
    db_session.add_all([category, foreign_category])
    db_session.flush()
    product = Product(category_id=category.id, name="Rice", base_price=Decimal("12.35"))
    foreign_product = Product(category_id=foreign_category.id, name="Other Rice", base_price=Decimal("9.00"))
    db_session.add_all([product, foreign_product])
    db_session.flush()
    variant = ProductVariant(product_id=product.id, name="Large", price_delta=Decimal("2.15"))
    foreign_variant = ProductVariant(product_id=foreign_product.id, name="Wrong", price_delta=Decimal("1.00"))
    db_session.add_all([variant, foreign_variant])
    address = Address(user_id=customer.id, label="Home", recipient_name="Alice", recipient_phone="123",
                      line1="3 Road", city="Accra", is_default=True)
    foreign_address = Address(user_id=other_customer.id, label="Home", recipient_name="Bob", recipient_phone="456",
                              line1="4 Road", city="Accra", is_default=True)
    db_session.add_all([address, foreign_address])
    db_session.commit()
    return locals()


def fill_cart(client, data, *, with_variant=True):
    customer, product, branch = data["customer"], data["product"], data["branch"]
    first = client.post("/cart/items", json={"product_id": str(product.id),
                                             "branch_id": str(branch.id), "quantity": 2}, headers=auth(customer))
    assert first.status_code == 201, first.text
    if with_variant:
        second = client.post("/cart/items", json={"product_id": str(product.id),
                                                  "product_variant_id": str(data["variant"].id),
                                                  "quantity": 1}, headers=auth(customer))
        assert second.status_code == 201, second.text
    return first.json()["id"]


def checkout(client, data):
    return client.post("/orders/checkout", json=checkout_payload(data["address"]),
                       headers=auth(data["customer"]))


def test_checkout_guards_empty_cart_and_address_validation(client, order_setup):
    data = order_setup
    payload = checkout_payload(data["address"])
    assert client.post("/orders/checkout", json=payload).status_code == 401
    for name in ("owner", "staff", "driver", "admin"):
        assert client.post("/orders/checkout", json=payload, headers=auth(data[name])).status_code == 403
    assert checkout(client, data).status_code == 409
    fill_cart(client, data)
    assert client.post("/orders/checkout", json={**payload, "total_amount": "0.01"},
                       headers=auth(data["customer"])).status_code == 422
    assert client.post("/orders/checkout", json={"address_id": "not-a-uuid", "payment_method": "CASH_ON_DELIVERY"},
                       headers=auth(data["customer"])).status_code == 422
    assert client.post("/orders/checkout", json={"address_id": str(data["address"].id),
                                                 "payment_method": "UNKNOWN"},
                       headers=auth(data["customer"])).status_code == 422
    assert client.post("/orders/checkout", json={"address_id": str(data["foreign_address"].id),
                                                 "payment_method": "CASH_ON_DELIVERY"},
                       headers=auth(data["customer"])).status_code == 404
    assert client.post("/orders/checkout", json={"address_id": str(UUID(int=1)),
                                                 "payment_method": "CASH_ON_DELIVERY"},
                       headers=auth(data["customer"])).status_code == 404
    assert client.get("/cart", headers=auth(data["customer"])).json()["branch_id"] == str(data["branch"].id)


@pytest.mark.parametrize("unavailable", ["branch", "restaurant", "menu", "category", "product", "variant"])
def test_checkout_revalidates_current_catalogue(client, order_setup, db_session, unavailable):
    data = order_setup
    fill_cart(client, data)
    target = data[unavailable]
    if unavailable in {"branch", "restaurant", "menu", "category"}:
        target.is_active = False
    else:
        target.is_available = False
    db_session.commit()
    response = checkout(client, data)
    assert response.status_code == 409, response.text
    assert db_session.scalar(select(func.count()).select_from(Order)) == 0
    assert db_session.scalar(select(func.count()).select_from(CartItem)) == 2


def test_checkout_rejects_stale_variant_relationship_and_branch_scope(client, order_setup, db_session):
    data = order_setup
    cart_id = fill_cart(client, data)
    variant_row = db_session.scalar(select(CartItem).where(CartItem.cart_id == UUID(cart_id),
                                                          CartItem.product_variant_id.is_not(None)))
    variant_row.product_variant_id = data["foreign_variant"].id
    db_session.commit()
    assert checkout(client, data).status_code == 409
    variant_row.product_variant_id = data["variant"].id
    db_session.get(Cart, UUID(cart_id)).branch_id = data["foreign_branch"].id
    db_session.commit()
    assert checkout(client, data).status_code == 409


def test_checkout_records_snapshots_payment_history_and_clears_cart(client, order_setup, db_session):
    data = order_setup
    cart_id = fill_cart(client, data)
    data["product"].base_price = Decimal("13.00")  # Checkout uses the current catalogue, not add-to-cart price.
    db_session.commit()
    result = checkout(client, data)
    assert result.status_code == 201, result.text
    body = result.json()
    assert body["status"] == "PENDING"
    assert Decimal(body["subtotal"]) == Decimal("41.15")
    assert Decimal(body["delivery_fee"]) == Decimal("0.00")
    assert Decimal(body["total_amount"]) == Decimal("41.15")
    assert len(body["items"]) == 2
    assert sorted(Decimal(row["unit_price"]) for row in body["items"]) == [Decimal("13.00"), Decimal("15.15")]
    assert sorted(Decimal(row["line_total"]) for row in body["items"]) == [Decimal("15.15"), Decimal("26.00")]
    assert body["delivery_address_snapshot"]["line1"] == "3 Road"
    assert body["payment_status"] == "PENDING"
    assert len(body["status_history"]) == 1
    assert body["status_history"][0]["from_status"] is None
    assert body["status_history"][0]["to_status"] == "PENDING"
    assert db_session.scalar(select(func.count()).select_from(Order)) == 1
    assert db_session.scalar(select(func.count()).select_from(OrderItem)) == 2
    assert db_session.scalar(select(func.count()).select_from(OrderStatusHistory)) == 1
    payment = db_session.scalar(select(Payment))
    assert payment.amount == Decimal("41.15") and payment.status == PaymentStatus.PENDING
    assert payment.currency == "GHS" and payment.provider == "CASH_ON_DELIVERY"
    assert db_session.scalar(select(func.count()).select_from(CartItem)) == 0
    assert db_session.get(Cart, UUID(cart_id)).branch_id is None
    assert checkout(client, data).status_code == 409
    assert db_session.scalar(select(func.count()).select_from(Order)) == 1

    data["product"].name = "Changed Rice"
    data["product"].base_price = Decimal("99.00")
    data["variant"].name = "Changed Large"
    data["variant"].price_delta = Decimal("9.00")
    data["address"].line1 = "Changed Road"
    db_session.commit()
    historic = client.get(f"/orders/{body['id']}", headers=auth(data["customer"]))
    assert historic.status_code == 200
    assert historic.json()["items"] == body["items"]
    assert historic.json()["delivery_address_snapshot"] == body["delivery_address_snapshot"]
    assert historic.json()["total_amount"] == body["total_amount"]


def test_checkout_failure_rolls_back_everything(client, order_setup, db_session, monkeypatch):
    data = order_setup
    cart_id = fill_cart(client, data)
    with monkeypatch.context() as patch:
        patch.setattr(db_session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("forced commit failure")))
        with pytest.raises(RuntimeError, match="forced commit failure"):
            checkout(client, data)
    assert db_session.scalar(select(func.count()).select_from(Order)) == 0
    assert db_session.scalar(select(func.count()).select_from(OrderItem)) == 0
    assert db_session.scalar(select(func.count()).select_from(OrderStatusHistory)) == 0
    assert db_session.scalar(select(func.count()).select_from(Payment)) == 0
    assert db_session.scalar(select(func.count()).select_from(CartItem)) == 2
    assert db_session.get(Cart, UUID(cart_id)).branch_id == data["branch"].id


def test_order_access_listing_and_idor(client, order_setup, db_session):
    data = order_setup
    fill_cart(client, data)
    order = checkout(client, data).json()
    path = f"/orders/{order['id']}"
    assert client.get("/orders").status_code == 401
    assert client.get(path).status_code == 401
    assert client.get("/orders/not-a-uuid", headers=auth(data["customer"])).status_code == 422
    assert client.get(path, headers=auth(data["customer"])).status_code == 200
    assert client.get("/orders", headers=auth(data["customer"])).json()["total"] == 1
    assert client.get("/orders", params={"status": "PENDING"}, headers=auth(data["customer"])).json()["total"] == 1
    assert client.get("/orders", params={"status": "CONFIRMED"}, headers=auth(data["customer"])).json()["total"] == 0
    assert client.get("/orders", headers=auth(data["other_customer"])).json()["total"] == 0
    assert client.get(path, headers=auth(data["other_customer"])).status_code == 404
    assert client.get(path, headers=auth(data["owner"])).status_code == 200
    assert client.get(path, headers=auth(data["staff"])).status_code == 200
    assert client.get(path, headers=auth(data["wrong_branch_staff"])).status_code == 404
    assert client.get(path, headers=auth(data["other_owner"])).status_code == 404
    assert client.get(path, headers=auth(data["other_staff"])).status_code == 404
    assert client.get(path, headers=auth(data["admin"])).status_code == 200
    assert client.get("/orders", headers=auth(data["owner"])).json()["total"] == 1
    assert client.get("/orders", headers=auth(data["admin"])).json()["total"] == 1
    membership = db_session.scalar(select(RestaurantStaff).where(RestaurantStaff.user_id == data["staff"].id))
    membership.is_active = False
    db_session.commit()
    assert client.get(path, headers=auth(data["staff"])).status_code == 404
    assert client.get("/orders", headers=auth(data["driver"])).status_code == 403
    assert client.get(f"{path}/status-history", headers=auth(data["other_customer"])).status_code == 404
    assert client.get("/orders", params={"page": 0}, headers=auth(data["customer"])).status_code == 422
    assert client.get("/orders", params={"status": "INVALID"}, headers=auth(data["customer"])).status_code == 422


def test_exact_state_machine_authorization_and_history(client, order_setup, db_session):
    data = order_setup
    fill_cart(client, data)
    order = checkout(client, data).json()
    path = f"/orders/{order['id']}/status"
    owner_headers = auth(data["owner"])
    admin_headers = auth(data["admin"])
    assert client.patch(path, json={"status": "CONFIRMED"}).status_code == 401
    assert client.patch(path, json={"status": "CONFIRMED"}, headers=auth(data["customer"])).status_code == 403
    assert client.patch(path, json={"status": "CONFIRMED"}, headers=auth(data["other_owner"])).status_code == 404
    assert client.patch(path, json={"status": "CONFIRMED"}, headers=auth(data["other_staff"])).status_code == 404
    assert client.patch(path, json={"status": "PREPARING"}, headers=owner_headers).status_code == 409
    assert client.patch(path, json={"status": "DELIVERED"}, headers=admin_headers).status_code == 409
    for target, headers in [
        ("CONFIRMED", owner_headers), ("PREPARING", auth(data["staff"])),
        ("READY_FOR_PICKUP", owner_headers), ("OUT_FOR_DELIVERY", admin_headers),
        ("DELIVERED", admin_headers),
    ]:
        response = client.patch(path, json={"status": target, "reason": "Progressed"}, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == target
    assert client.patch(path, json={"status": "DELIVERED"}, headers=admin_headers).status_code == 409
    assert client.patch(path, json={"status": "CONFIRMED"}, headers=admin_headers).status_code == 409
    history = client.get(f"/orders/{order['id']}/status-history", headers=auth(data["customer"]))
    assert history.status_code == 200
    assert [row["to_status"] for row in history.json()] == [state.value for state in OrderStatus]
    assert len(history.json()) == 6
    assert [row["from_status"] for row in history.json()] == [None] + [state.value for state in list(OrderStatus)[:-1]]
    assert [row["created_at"] for row in history.json()] == sorted(row["created_at"] for row in history.json())
    assert all(row["changed_by_user_id"] is not None for row in history.json())
    assert db_session.scalar(select(func.count()).select_from(OrderStatusHistory)) == 6


def test_delivery_steps_denied_to_restaurant_and_driver(client, order_setup):
    data = order_setup
    fill_cart(client, data)
    order = checkout(client, data).json()
    path = f"/orders/{order['id']}/status"
    for target in ("CONFIRMED", "PREPARING", "READY_FOR_PICKUP"):
        assert client.patch(path, json={"status": target}, headers=auth(data["owner"])).status_code == 200
    assert client.patch(path, json={"status": "OUT_FOR_DELIVERY"}, headers=auth(data["owner"])).status_code == 403
    assert client.patch(path, json={"status": "OUT_FOR_DELIVERY"}, headers=auth(data["staff"])).status_code == 403
    assert client.patch(path, json={"status": "OUT_FOR_DELIVERY"}, headers=auth(data["driver"])).status_code == 403
    assert client.get(f"/orders/{order['id']}", headers=auth(data["customer"])).json()["status"] == "READY_FOR_PICKUP"


def test_stage6_openapi_contract(client):
    document = client.get("/openapi.json").json()
    required = {
        ("/orders/checkout", "post"), ("/orders", "get"),
        ("/orders/{order_id}", "get"),
        ("/orders/{order_id}/status-history", "get"),
        ("/orders/{order_id}/status", "patch"),
    }
    for path, method in required:
        operation = document["paths"][path][method]
        assert operation["tags"] == ["Orders"]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert "200" in operation["responses"] or "201" in operation["responses"]
    ids = [operation["operationId"] for methods in document["paths"].values()
           for method, operation in methods.items() if method in {"get", "post", "patch", "delete"}]
    assert len(ids) == len(set(ids))
    assert "password_hash" not in str(document["components"]["schemas"])


def test_stage6_api_driven_end_to_end_flow(client, db_session):
    """Only privileged actors are seeded; catalogue and customer flow use public APIs."""
    owner = User(email="api-order-owner@example.com", password_hash=hash_password("password123"),
                 full_name="Order Owner", role=UserRole.RESTAURANT_OWNER, is_active=True)
    unrelated_owner = User(email="api-order-unrelated@example.com", password_hash=hash_password("password123"),
                           full_name="Unrelated Owner", role=UserRole.RESTAURANT_OWNER, is_active=True)
    admin = User(email="api-order-admin@example.com", password_hash=hash_password("password123"),
                 full_name="Admin", role=UserRole.ADMIN, is_active=True)
    db_session.add_all([owner, unrelated_owner, admin])
    db_session.commit()
    owner_login = client.post("/auth/login", json={"email": owner.email, "password": "password123"})
    assert owner_login.status_code == 200
    owner_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}
    restaurant = client.post("/restaurants", json={"name": "API Order Kitchen", "slug": "api-order-kitchen"},
                             headers=owner_headers)
    assert restaurant.status_code == 201
    rid = restaurant.json()["id"]
    branch = client.post(f"/restaurants/{rid}/branches", json={"name": "Main", "line1": "1 Road", "city": "Accra"},
                         headers=owner_headers)
    assert branch.status_code == 201
    menu = client.post(f"/restaurants/{rid}/menus", json={"name": "Dinner"}, headers=owner_headers)
    assert menu.status_code == 201
    category = client.post(f"/menus/{menu.json()['id']}/categories", json={"name": "Mains"}, headers=owner_headers)
    assert category.status_code == 201
    product = client.post("/products", json={"category_id": category.json()["id"], "name": "Rice",
                                         "base_price": "10.00"}, headers=owner_headers)
    assert product.status_code == 201
    variant = client.post(f"/products/{product.json()['id']}/variants", json={"name": "Large",
                                                                              "price_override": "14.00"},
                          headers=owner_headers)
    assert variant.status_code == 201
    registered = client.post("/auth/register", json={"email": "api-order-customer@example.com",
                                                   "password": "password123", "full_name": "Alice"})
    assert registered.status_code == 201
    login = client.post("/auth/login", json={"email": "api-order-customer@example.com",
                                               "password": "password123"})
    assert login.status_code == 200
    customer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    address = client.post("/customers/me/addresses", json={"label": "Home", "recipient_name": "Alice",
                                                           "recipient_phone": "123", "line1": "2 Road",
                                                           "city": "Accra", "is_default": True},
                          headers=customer_headers)
    assert address.status_code == 201
    assert client.post("/cart/items", json={"product_id": product.json()["id"],
                                            "branch_id": branch.json()["id"], "quantity": 1},
                       headers=customer_headers).status_code == 201
    assert client.post("/cart/items", json={"product_id": product.json()["id"],
                                            "product_variant_id": variant.json()["id"], "quantity": 1},
                       headers=customer_headers).status_code == 201
    order = client.post("/orders/checkout", json={"address_id": address.json()["id"],
                                                   "payment_method": "MOBILE_MONEY"},
                        headers=customer_headers)
    assert order.status_code == 201, order.text
    body = order.json()
    assert body["status"] == "PENDING" and Decimal(body["total_amount"]) == Decimal("24.00")
    assert len(body["items"]) == 2 and len(body["status_history"]) == 1
    assert db_session.scalar(select(Payment).where(Payment.order_id == UUID(body["id"]))).status == PaymentStatus.PENDING
    cart = client.get("/cart", headers=customer_headers).json()
    assert cart["items"] == [] and cart["branch_id"] is None
    assert client.get(f"/orders/{body['id']}", headers=customer_headers).status_code == 200
    other = client.post("/auth/register", json={"email": "api-order-other@example.com",
                                              "password": "password123", "full_name": "Other"})
    assert other.status_code == 201
    other_login = client.post("/auth/login", json={"email": "api-order-other@example.com",
                                                     "password": "password123"})
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
    assert client.get(f"/orders/{body['id']}", headers=other_headers).status_code == 404
    assert client.get(f"/orders/{body['id']}", headers=auth(unrelated_owner)).status_code == 404
    status_path = f"/orders/{body['id']}/status"
    for target in ("CONFIRMED", "PREPARING", "READY_FOR_PICKUP"):
        assert client.patch(status_path, json={"status": target}, headers=owner_headers).status_code == 200
    for target in ("OUT_FOR_DELIVERY", "DELIVERED"):
        assert client.patch(status_path, json={"status": target}, headers=auth(admin)).status_code == 200
    assert client.patch(status_path, json={"status": "CONFIRMED"}, headers=auth(admin)).status_code == 409
    history = client.get(f"/orders/{body['id']}/status-history", headers=customer_headers).json()
    assert [entry["to_status"] for entry in history] == [state.value for state in OrderStatus]
    assert client.patch(f"/products/{product.json()['id']}", json={"name": "Changed Rice", "base_price": "99.00"},
                        headers=owner_headers).status_code == 200
    assert client.patch(f"/customers/me/addresses/{address.json()['id']}", json={"line1": "Changed Road"},
                        headers=customer_headers).status_code == 200
    historic = client.get(f"/orders/{body['id']}", headers=customer_headers).json()
    assert historic["items"] == body["items"]
    assert historic["delivery_address_snapshot"] == body["delivery_address_snapshot"]
