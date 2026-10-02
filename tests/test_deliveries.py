"""Stage 8 dispatch, assigned-driver permissions, histories, and atomic synchronization."""
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.core.enums import DeliveryStatus, OrderStatus, UserRole
from app.core.security import hash_password
from app.models.delivery import Delivery, DeliveryStatusHistory, Driver
from app.models.identity import User
from app.models.ordering import Order, OrderStatusHistory
from app.models.restaurant import RestaurantStaff
from test_orders import auth, checkout, fill_cart, order_setup  # noqa: F401


def ready_order(client, data):
    fill_cart(client, data)
    response = checkout(client, data)
    assert response.status_code == 201, response.text
    order = response.json()
    for target in ("CONFIRMED", "PREPARING", "READY_FOR_PICKUP"):
        response = client.patch(f"/orders/{order['id']}/status", json={"status": target},
                                headers=auth(data["owner"]))
        assert response.status_code == 200, response.text
    return order


def create_delivery(client, data, order=None, actor="owner"):
    order = order or ready_order(client, data)
    response = client.post(f"/orders/{order['id']}/delivery", json={}, headers=auth(data[actor]))
    assert response.status_code == 201, response.text
    return response.json()


def create_driver(client, data, user=None, **fields):
    response = client.post("/drivers", json={"user_id": str((user or data["driver"]).id),
                                             "vehicle_type": "motorcycle", **fields},
                           headers=auth(data["admin"]))
    assert response.status_code == 201, response.text
    return response.json()


def second_driver(db_session):
    user = User(email="other-delivery-driver@example.com", password_hash=hash_password("password123"),
                full_name="Other Driver", role=UserRole.DRIVER, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def assign(client, data, delivery, driver, actor="owner"):
    return client.patch(f"/deliveries/{delivery['id']}/assign", json={"driver_id": driver["id"]},
                        headers=auth(data[actor]))


def progress(client, data, delivery, status, actor="driver"):
    return client.patch(f"/deliveries/{delivery['id']}/status", json={"status": status},
                        headers=auth(data[actor]))


def test_driver_profiles_creation_and_permissions(client, order_setup, db_session):
    data = order_setup
    assert client.get("/drivers/me").status_code == 401
    assert client.get("/drivers/me", headers=auth(data["driver"])).status_code == 404
    for name in ("customer", "owner", "staff"):
        assert client.get("/drivers", headers=auth(data[name])).status_code == 403
        assert client.get("/drivers/me", headers=auth(data[name])).status_code == 403
        assert client.post("/drivers", json={"user_id": str(data["driver"].id), "vehicle_type": "bike"},
                           headers=auth(data[name])).status_code == 403
    admin = auth(data["admin"])
    for user_id, code in ((data["customer"].id, 409), (uuid4(), 404)):
        assert client.post("/drivers", json={"user_id": str(user_id), "vehicle_type": "bike"},
                           headers=admin).status_code == code
    driver = create_driver(client, data, vehicle_identifier="BIKE-1")
    assert client.post("/drivers", json={"user_id": str(data["driver"].id), "vehicle_type": "bike"},
                       headers=admin).status_code == 409
    assert client.get("/drivers", headers=admin).json() == [driver]
    path = f"/drivers/{driver['id']}"
    assert client.get(path, headers=admin).json() == driver
    assert client.get("/drivers/me", headers=auth(data["driver"])).json() == driver
    assert client.get(path, headers=auth(data["customer"])).status_code == 403
    other = second_driver(db_session)
    create_driver(client, data, other)
    assert client.patch(path, json={"is_available": False}, headers=auth(other)).status_code == 404
    for payload in ({"user_id": str(other.id)}, {"vehicle_type": None}, {"is_available": None},
                    {"vehicle_type": "  "}, {"is_active": False}):
        assert client.patch(path, json=payload, headers=admin).status_code == 422
    updated = client.patch(path, json={"vehicle_type": "car", "is_available": False},
                           headers=auth(data["driver"]))
    assert updated.status_code == 200 and updated.json()["vehicle_type"] == "car"
    assert client.patch(path, json={"is_available": True}, headers=admin).status_code == 200
    data["driver"].is_active = False
    db_session.commit()
    assert client.get("/drivers/me", headers=auth(data["driver"])).status_code == 401
    assert client.patch(path, json={"is_available": True}, headers=auth(data["driver"])).status_code == 401


def test_delivery_creation_validation_and_initial_history(client, order_setup, db_session):
    data = order_setup
    fill_cart(client, data)
    order = checkout(client, data).json()
    path = f"/orders/{order['id']}/delivery"
    assert client.post(path, json={}).status_code == 401
    for name in ("customer", "driver"):
        assert client.post(path, json={}, headers=auth(data[name])).status_code == 403
    for name in ("other_owner", "other_staff", "wrong_branch_staff"):
        assert client.post(path, json={}, headers=auth(data[name])).status_code == 404
    assert client.post(path, json={}, headers=auth(data["owner"])).status_code == 409
    assert client.post(f"/orders/{uuid4()}/delivery", json={}, headers=auth(data["admin"])).status_code == 404
    assert client.post("/orders/invalid/delivery", json={}, headers=auth(data["admin"])).status_code == 422
    for target in ("CONFIRMED", "PREPARING", "READY_FOR_PICKUP"):
        assert client.patch(f"/orders/{order['id']}/status", json={"status": target},
                            headers=auth(data["owner"])).status_code == 200
    assert client.post(path, json={"status": "ASSIGNED"}, headers=auth(data["owner"])).status_code == 422
    delivery = create_delivery(client, data, order, actor="staff")
    assert delivery["status"] == "UNASSIGNED" and delivery["driver_id"] is None
    assert client.post(path, json={}, headers=auth(data["admin"])).status_code == 409
    history = client.get(f"/deliveries/{delivery['id']}/status-history", headers=auth(data["customer"])).json()
    assert len(history) == 1 and history[0]["from_status"] is None
    assert history[0]["to_status"] == "UNASSIGNED"
    assert history[0]["changed_by_user_id"] == str(data["staff"].id)
    assert db_session.scalar(select(func.count()).select_from(Delivery)) == 1
    assert create_delivery(client, data, actor="admin")["status"] == "UNASSIGNED"


def test_assignment_eligibility_and_role_guards(client, order_setup, db_session):
    data = order_setup
    delivery = create_delivery(client, data)
    driver = create_driver(client, data)
    path = f"/deliveries/{delivery['id']}/assign"
    assert client.patch(path, json={"driver_id": driver["id"]}).status_code == 401
    for name in ("customer", "driver"):
        assert assign(client, data, delivery, driver, name).status_code == 403
    for name in ("other_owner", "other_staff", "wrong_branch_staff"):
        assert assign(client, data, delivery, driver, name).status_code == 404
    assert assign(client, data, delivery, {"id": str(uuid4())}).status_code == 404
    assert assign(client, data, {"id": str(uuid4())}, driver).status_code == 404
    assert assign(client, data, delivery, {"id": "invalid"}).status_code == 422
    row = db_session.get(Driver, UUID(driver["id"]))
    for attribute, invalid, restored in (("is_active", False, True), ("role", UserRole.CUSTOMER, UserRole.DRIVER)):
        setattr(data["driver"], attribute, invalid)
        db_session.commit()
        assert assign(client, data, delivery, driver).status_code == 409
        setattr(data["driver"], attribute, restored)
        db_session.commit()
    row.is_available = False
    db_session.commit()
    assert assign(client, data, delivery, driver).status_code == 409
    row.is_available = True
    db_session.commit()
    assigned = assign(client, data, delivery, driver, "staff")
    assert assigned.status_code == 200 and assigned.json()["status"] == "ASSIGNED"
    assert assigned.json()["assigned_at"] is not None
    assert assign(client, data, delivery, driver).status_code == 409


def test_reassignment_preserves_history_and_driver_scope(client, order_setup, db_session):
    data = order_setup
    delivery = create_delivery(client, data)
    driver = create_driver(client, data)
    other = second_driver(db_session)
    replacement = create_driver(client, data, other)
    assert assign(client, data, delivery, driver).status_code == 200
    history_path = f"/deliveries/{delivery['id']}/status-history"
    original = client.get(history_path, headers=auth(data["customer"])).json()
    assert assign(client, data, delivery, replacement, "admin").status_code == 200
    history = client.get(history_path, headers=auth(data["customer"])).json()
    assert history[:2] == original
    assert history[-1]["from_status"] == history[-1]["to_status"] == "ASSIGNED"
    assert driver["id"] in history[-1]["note"] and replacement["id"] in history[-1]["note"]
    assert history[-1]["changed_by_user_id"] == str(data["admin"].id)
    assert progress(client, data, delivery, "PICKED_UP").status_code == 404
    assert client.get("/drivers/me/deliveries", headers=auth(data["driver"])).json() == []
    assert client.patch(f"/deliveries/{delivery['id']}/status", json={"status": "PICKED_UP"},
                        headers=auth(other)).status_code == 200
    assert assign(client, data, delivery, driver).status_code == 409


def test_active_delivery_conflict_and_unavailability_safety(client, order_setup):
    data = order_setup
    first, second = create_delivery(client, data), create_delivery(client, data)
    driver = create_driver(client, data)
    assert assign(client, data, first, driver).status_code == 200
    for state in ("ASSIGNED", "PICKED_UP", "IN_TRANSIT"):
        if state != "ASSIGNED":
            assert progress(client, data, first, state).status_code == 200
        assert assign(client, data, second, driver).status_code == 409
        for actor in ("admin", "driver"):
            assert client.patch(f"/drivers/{driver['id']}", json={"is_available": False},
                                headers=auth(data[actor])).status_code == 409
    assert progress(client, data, first, "DELIVERED").status_code == 200
    assert assign(client, data, second, driver).status_code == 200


def test_delivery_visibility_and_active_memberships(client, order_setup, db_session):
    data = order_setup
    delivery = create_delivery(client, data)
    driver = create_driver(client, data)
    other = second_driver(db_session)
    create_driver(client, data, other)
    assert assign(client, data, delivery, driver).status_code == 200
    path = f"/deliveries/{delivery['id']}"
    for suffix in ("", "/status-history"):
        assert client.get(path + suffix).status_code == 401
        for name in ("customer", "owner", "staff", "admin", "driver"):
            assert client.get(path + suffix, headers=auth(data[name])).status_code == 200
        for name in ("other_customer", "other_owner", "other_staff", "wrong_branch_staff"):
            assert client.get(path + suffix, headers=auth(data[name])).status_code == 404
        assert client.get(path + suffix, headers=auth(other)).status_code == 404
    for name in ("other_customer", "other_owner", "wrong_branch_staff"):
        assert client.get("/deliveries", headers=auth(data[name])).json() == []
    for name in ("customer", "owner", "staff", "admin", "driver"):
        assert len(client.get("/deliveries", headers=auth(data[name])).json()) == 1
    assert len(client.get("/drivers/me/deliveries", headers=auth(data["driver"])).json()) == 1
    assert client.get("/drivers/me/deliveries", headers=auth(data["customer"])).status_code == 403
    membership = db_session.scalar(select(RestaurantStaff).where(RestaurantStaff.user_id == data["staff"].id))
    membership.is_active = False
    db_session.commit()
    assert client.get(path, headers=auth(data["staff"])).status_code == 404
    assert client.patch(path + "/status", json={"status": "PICKED_UP"}, headers=auth(other)).status_code == 404
    assert client.get(f"/deliveries/{uuid4()}", headers=auth(data["admin"])).status_code == 404
    assert client.get("/deliveries/bad", headers=auth(data["admin"])).status_code == 422


def test_delivery_state_machine_order_sync_and_immutable_history(client, order_setup):
    data = order_setup
    order = ready_order(client, data)
    delivery = create_delivery(client, data, order)
    driver = create_driver(client, data)
    assert progress(client, data, delivery, "PICKED_UP", "admin").status_code == 409
    assert progress(client, data, delivery, "ASSIGNED", "admin").status_code == 409
    assert assign(client, data, delivery, driver).status_code == 200
    for name in ("owner", "staff", "customer"):
        assert progress(client, data, delivery, "PICKED_UP", name).status_code == 403
    assert client.patch(f"/deliveries/{delivery['id']}/status", json={"status": "PICKED_UP"}).status_code == 401
    assert progress(client, data, delivery, "INVALID").status_code == 422
    assert client.patch(f"/orders/{order['id']}/status", json={"status": "OUT_FOR_DELIVERY"},
                        headers=auth(data["admin"])).status_code == 409
    for invalid in ("UNASSIGNED", "ASSIGNED", "IN_TRANSIT", "DELIVERED"):
        assert progress(client, data, delivery, invalid).status_code == 409
    path = f"/deliveries/{delivery['id']}/status-history"
    previous = client.get(path, headers=auth(data["customer"])).json()
    assert client.get(f"/orders/{order['id']}", headers=auth(data["customer"])).json()["status"] == "READY_FOR_PICKUP"
    for target, order_status in (("PICKED_UP", "OUT_FOR_DELIVERY"), ("IN_TRANSIT", "OUT_FOR_DELIVERY"),
                                 ("DELIVERED", "DELIVERED")):
        response = progress(client, data, delivery, target)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == target
        assert client.get(f"/orders/{order['id']}", headers=auth(data["customer"])).json()["status"] == order_status
        history = client.get(path, headers=auth(data["customer"])).json()
        assert history[:-1] == previous
        previous = history
        assert progress(client, data, delivery, target).status_code == 409
        assert progress(client, data, delivery, "ASSIGNED").status_code == 409
        if target == "PICKED_UP":
            assert progress(client, data, delivery, "DELIVERED").status_code == 409
    assert [row["to_status"] for row in previous] == [state.value for state in DeliveryStatus]
    assert [row["created_at"] for row in previous] == sorted(row["created_at"] for row in previous)
    assert all(row["changed_by_user_id"] for row in previous)
    order_history = client.get(f"/orders/{order['id']}/status-history", headers=auth(data["customer"])).json()
    assert [row["to_status"] for row in order_history] == [state.value for state in OrderStatus]
    assert all(row["changed_by_user_id"] == str(data["driver"].id) for row in order_history[-2:])
    assert assign(client, data, delivery, driver).status_code == 409
    assert client.delete(f"/deliveries/{delivery['id']}", headers=auth(data["admin"])).status_code == 405


@pytest.mark.parametrize("target", ["PICKED_UP", "DELIVERED"])
def test_synchronized_transition_rollback(client, order_setup, db_session, monkeypatch, target):
    data = order_setup
    order = ready_order(client, data)
    delivery = create_delivery(client, data, order)
    driver = create_driver(client, data)
    assert assign(client, data, delivery, driver).status_code == 200
    if target == "DELIVERED":
        for state in ("PICKED_UP", "IN_TRANSIT"):
            assert progress(client, data, delivery, state).status_code == 200
    path = f"/deliveries/{delivery['id']}"
    before_delivery = client.get(path, headers=auth(data["customer"])).json()
    before_history = client.get(path + "/status-history", headers=auth(data["customer"])).json()
    before_order = client.get(f"/orders/{order['id']}", headers=auth(data["customer"])).json()
    with monkeypatch.context() as patch:
        def fail_commit():
            raise RuntimeError("forced synchronization failure")
        patch.setattr(db_session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="forced synchronization failure"):
            progress(client, data, delivery, target)
    assert client.get(path, headers=auth(data["customer"])).json() == before_delivery
    assert client.get(path + "/status-history", headers=auth(data["customer"])).json() == before_history
    assert client.get(f"/orders/{order['id']}", headers=auth(data["customer"])).json() == before_order


def test_admin_transitions_and_order_consistency_guards(client, order_setup, db_session):
    data = order_setup
    order = ready_order(client, data)
    delivery = create_delivery(client, data, order)
    driver = create_driver(client, data)
    row = db_session.get(Order, UUID(order["id"]))
    row.status = OrderStatus.PREPARING
    db_session.commit()
    assert assign(client, data, delivery, driver).status_code == 409
    row.status = OrderStatus.READY_FOR_PICKUP
    db_session.commit()
    assert assign(client, data, delivery, driver).status_code == 200
    row.status = OrderStatus.DELIVERED
    db_session.commit()
    assert progress(client, data, delivery, "PICKED_UP", "admin").status_code == 409
    row.status = OrderStatus.READY_FOR_PICKUP
    db_session.commit()
    for state in ("PICKED_UP", "IN_TRANSIT", "DELIVERED"):
        assert progress(client, data, delivery, state, "admin").status_code == 200


def test_stage8_openapi_contract(client):
    document = client.get("/openapi.json").json()
    routes = {
        "/drivers": ("get", "post"), "/drivers/me": ("get",),
        "/drivers/me/deliveries": ("get",), "/drivers/{driver_id}": ("get", "patch"),
        "/orders/{order_id}/delivery": ("post",), "/deliveries": ("get",),
        "/deliveries/{delivery_id}": ("get",), "/deliveries/{delivery_id}/status-history": ("get",),
        "/deliveries/{delivery_id}/assign": ("patch",), "/deliveries/{delivery_id}/status": ("patch",),
    }
    for path, methods in routes.items():
        for method in methods:
            operation = document["paths"][path][method]
            assert operation["security"] == [{"HTTPBearer": []}]
            assert operation["tags"] == ["Drivers" if path.startswith("/drivers") else "Deliveries"]
            for parameter in operation.get("parameters", []):
                if parameter["in"] == "path":
                    assert parameter["schema"]["format"] == "uuid"
    schemas = document["components"]["schemas"]
    assert schemas["DeliveryAssign"]["properties"]["driver_id"]["format"] == "uuid"
    assert schemas["DeliveryTransition"]["properties"]["status"]["$ref"].endswith("/DeliveryStatus")
    assert schemas["DeliveryStatus"]["enum"] == [state.value for state in DeliveryStatus]
    assert "user_id" not in schemas["DriverUpdate"]["properties"]
    for name in ("DriverResponse", "DeliveryResponse", "DeliveryHistoryResponse"):
        assert not {"password", "password_hash", "email", "phone", "secret"} & schemas[name]["properties"].keys()
    ids = [op["operationId"] for methods in document["paths"].values() for method, op in methods.items()
           if method in ("get", "post", "patch", "delete")]
    assert len(ids) == len(set(ids))


def test_stage8_api_end_to_end_and_financial_integrity(client, order_setup, db_session):
    data = order_setup
    order = ready_order(client, data)
    payment = client.get(f"/orders/{order['id']}/payments", headers=auth(data["customer"])).json()[0]
    assert client.post(f"/payments/{payment['id']}/confirm", headers=auth(data["admin"])).status_code == 200
    assert client.post(f"/payments/{payment['id']}/refunds", json={"amount": "1.00", "reason": "Adjustment"},
                       headers=auth(data["admin"])).status_code == 201
    payment_path = f"/payments/{payment['id']}"
    customer_headers = auth(data["customer"])
    original_payment = client.get(payment_path, headers=customer_headers).json()
    original_refunds = client.get(payment_path + "/refunds", headers=customer_headers).json()
    original_cart = client.get("/cart", headers=customer_headers).json()
    original_order = client.get(f"/orders/{order['id']}", headers=customer_headers).json()
    delivery = create_delivery(client, data, order)
    driver = create_driver(client, data)
    assert assign(client, data, delivery, driver).status_code == 200
    login = client.post("/auth/login", json={"email": data["driver"].email, "password": "password123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    for state, expected in (("PICKED_UP", "OUT_FOR_DELIVERY"), ("IN_TRANSIT", "OUT_FOR_DELIVERY"),
                            ("DELIVERED", "DELIVERED")):
        response = client.patch(f"/deliveries/{delivery['id']}/status", json={"status": state}, headers=headers)
        assert response.status_code == 200
        assert client.get(f"/orders/{order['id']}", headers=customer_headers).json()["status"] == expected
    assert progress(client, data, delivery, "PICKED_UP").status_code == 409
    other = second_driver(db_session)
    create_driver(client, data, other)
    assert client.patch(f"/deliveries/{delivery['id']}/status", json={"status": "DELIVERED"},
                        headers=auth(other)).status_code == 404
    for actor in ("other_customer", "other_owner"):
        assert client.get(f"/deliveries/{delivery['id']}", headers=auth(data[actor])).status_code == 404
    assert client.get(payment_path, headers=customer_headers).json() == original_payment
    assert client.get(payment_path + "/refunds", headers=customer_headers).json() == original_refunds
    assert client.get("/cart", headers=customer_headers).json() == original_cart
    final_order = client.get(f"/orders/{order['id']}", headers=customer_headers).json()
    assert final_order["items"] == original_order["items"]
    assert final_order["delivery_address_snapshot"] == original_order["delivery_address_snapshot"]
    assert final_order["status_history"][:4] == original_order["status_history"]
    assert len(final_order["status_history"]) == 6
    history = client.get(f"/deliveries/{delivery['id']}/status-history", headers=headers).json()
    assert [row["to_status"] for row in history] == [state.value for state in DeliveryStatus]
