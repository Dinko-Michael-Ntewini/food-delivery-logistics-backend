"""Safe normalized errors, constraint rollback, and unchanged workflow states."""
from typing import Annotated
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import install_error_handlers
from app.db.session import get_db
from app.models.restaurant import Restaurant
from test_orders import auth, order_setup  # noqa: F401
from test_deliveries import ready_order, create_delivery, create_driver, assign, progress


def assert_error(response, status, code=None):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    error = body["error"]
    assert set(error) == {"code", "message", "details"}
    assert isinstance(error["message"], str) and error["message"]
    if code:
        assert error["code"] == code
    for forbidden in ("Traceback", "sqlalchemy", "sqlite", "postgresql://", "password_hash", "SECRET_KEY"):
        assert forbidden not in response.text
    return error


def test_authentication_and_wrong_role_errors_across_domains(client, order_setup):
    data = order_setup
    for path in ("/orders", "/cart", "/drivers/me", "/deliveries", f"/payments/{uuid4()}"):
        response = client.get(path)
        assert_error(response, 401, "UNAUTHORIZED")
        assert response.headers["www-authenticate"] == "Bearer"
    for path, actor in (("/drivers", "customer"), ("/orders", "driver"), ("/cart", "owner")):
        assert_error(client.get(path, headers=auth(data[actor])), 403, "FORBIDDEN")


def test_public_missing_resource_errors(client):
    for path in ("/restaurants", "/branches", "/menus", "/categories", "/products"):
        assert_error(client.get(f"{path}/{uuid4()}"), 404, "NOT_FOUND")
    assert_error(client.get("/unknown-route"), 404, "NOT_FOUND")


def test_protected_missing_resource_errors(client, order_setup):
    data = order_setup
    for path in (f"/orders/{uuid4()}", f"/payments/{uuid4()}", f"/refunds/{uuid4()}",
                 f"/drivers/{uuid4()}", f"/deliveries/{uuid4()}"):
        assert_error(client.get(path, headers=auth(data["admin"])), 404, "NOT_FOUND")
    assert_error(client.patch(f"/variants/{uuid4()}", json={"name": "Missing"}, headers=auth(data["admin"])), 404)
    assert_error(client.patch(f"/customers/me/addresses/{uuid4()}", json={"city": "Missing"},
                              headers=auth(data["customer"])), 404)
    assert_error(client.patch(f"/cart/items/{uuid4()}", json={"quantity": 1},
                              headers=auth(data["customer"])), 404)


def test_uuid_enum_body_and_query_validation_does_not_echo_inputs(client, order_setup):
    data = order_setup
    secret = "stage9-password-sentinel-should-not-be-echoed"
    response = client.post("/auth/register", json={"email": "invalid", "password": secret, "full_name": ""})
    details = assert_error(response, 422, "VALIDATION_ERROR")["details"]
    assert secret not in response.text
    assert all(set(detail) == {"location", "message", "type"} for detail in details)
    assert any(detail["location"] == ["body", "email"] for detail in details)
    cases = [client.get("/products/not-a-uuid"), client.get("/products", params={"category_id": "bad"}),
             client.post("/orders/checkout", json={"address_id": "bad", "payment_method": "bad"},
                         headers=auth(data["customer"])),
             client.get("/orders", params={"status": "bad"}, headers=auth(data["customer"]))]
    for response in cases:
        assert assert_error(response, 422, "VALIDATION_ERROR")["details"]


def test_conflict_and_state_machine_errors_preserve_records(client, order_setup):
    data = order_setup
    order = ready_order(client, data)
    original_order = client.get(f"/orders/{order['id']}", headers=auth(data["customer"])).json()
    response = client.patch(f"/orders/{order['id']}/status", json={"status": "DELIVERED"}, headers=auth(data["admin"]))
    assert_error(response, 409, "INVALID_TRANSITION")
    assert client.get(f"/orders/{order['id']}", headers=auth(data["customer"])).json() == original_order
    payment = client.get(f"/orders/{order['id']}/payments", headers=auth(data["customer"])).json()[0]
    path = f"/payments/{payment['id']}"
    assert client.post(path + "/confirm", headers=auth(data["admin"])).status_code == 200
    original_payment = client.get(path, headers=auth(data["customer"])).json()
    assert_error(client.post(path + "/fail", headers=auth(data["admin"])), 409, "INVALID_TRANSITION")
    assert client.get(path, headers=auth(data["customer"])).json() == original_payment
    assert_error(client.post(path + "/refunds", json={"amount": "999.00", "reason": "Too much"},
                             headers=auth(data["admin"])), 409, "CONFLICT")
    delivery = create_delivery(client, data, order)
    driver = create_driver(client, data)
    assert assign(client, data, delivery, driver).status_code == 200
    delivery_path = f"/deliveries/{delivery['id']}"
    original_delivery = client.get(delivery_path, headers=auth(data["customer"])).json()
    original_history = client.get(delivery_path + "/status-history", headers=auth(data["customer"])).json()
    assert_error(progress(client, data, delivery, "DELIVERED"), 409, "INVALID_TRANSITION")
    assert client.get(delivery_path, headers=auth(data["customer"])).json() == original_delivery
    assert client.get(delivery_path + "/status-history", headers=auth(data["customer"])).json() == original_history
    assert_error(client.post(f"/orders/{order['id']}/delivery", json={}, headers=auth(data["owner"])), 409, "CONFLICT")


def test_constraint_race_service_rolls_back_and_remains_usable(client, order_setup, db_session, monkeypatch):
    from sqlalchemy.exc import IntegrityError
    data = order_setup
    original_commit = db_session.commit
    calls = []
    original_rollback = db_session.rollback
    def rollback():
        calls.append("rollback")
        original_rollback()
    with monkeypatch.context() as patch:
        patch.setattr(db_session, "rollback", rollback)
        patch.setattr(db_session, "commit", lambda: (_ for _ in ()).throw(
            IntegrityError("INSERT secret SQL", {"password": "private"}, Exception("private database URL"))))
        response = client.post(f"/restaurants/{data['restaurant'].id}/branches", json={"name": "Race",
                               "line1": "1 Street", "city": "Accra"}, headers=auth(data["owner"]))
        assert_error(response, 409, "CONFLICT")
        assert "secret SQL" not in response.text and "private" not in response.text
    assert calls == ["rollback"]
    assert db_session.commit == original_commit
    response = client.post(f"/restaurants/{data['restaurant'].id}/branches", json={"name": "Race",
                           "line1": "1 Street", "city": "Accra"}, headers=auth(data["owner"]))
    assert response.status_code == 201


def test_uncaught_integrity_error_dependency_rollback_and_handler(db_session, monkeypatch):
    """Exercise the real get_db lifecycle and fallback with an actual unique violation."""
    import app.db.session as session_module
    db_session.add(Restaurant(name="Existing", slug="unique-stage9"))
    db_session.commit()
    original_rollback = db_session.rollback
    calls = []
    def rollback():
        calls.append("rollback")
        original_rollback()
    monkeypatch.setattr(db_session, "rollback", rollback)
    monkeypatch.setattr(session_module, "SessionLocal", lambda: db_session)
    application = FastAPI()
    install_error_handlers(application)
    @application.post("/conflict")
    def conflict(db: Annotated[Session, Depends(get_db)]):
        db.add(Restaurant(name="Duplicate", slug="unique-stage9"))
        db.flush()
    @application.get("/usable")
    def usable(db: Annotated[Session, Depends(get_db)]):
        return {"total": db.scalar(select(func.count()).select_from(Restaurant))}
    with TestClient(application) as test_client:
        assert_error(test_client.post("/conflict"), 409, "CONFLICT")
        assert calls == ["rollback"]
        assert test_client.get("/usable").json() == {"total": 1}


def test_unexpected_failure_is_generic_and_has_no_traceback():
    application = FastAPI(debug=False)
    install_error_handlers(application)
    @application.get("/failure")
    def failure():
        raise RuntimeError("SELECT password_hash FROM users; SECRET_KEY=private; C:/private/path")
    with TestClient(application, raise_server_exceptions=False) as test_client:
        response = test_client.get("/failure")
        assert_error(response, 500, "INTERNAL_ERROR")
        assert response.json()["error"]["message"] == "Internal server error"
        assert "private" not in response.text and "SELECT" not in response.text


def test_stage9_openapi_filters_security_pagination_and_error_schemas(client):
    document = client.get("/openapi.json").json()
    required = {
        "/orders": {"status", "restaurant_id", "branch_id", "customer_id", "date_from", "date_to", "search", "page", "page_size", "sort"},
        "/products": {"search", "category_id", "restaurant_id", "min_price", "max_price", "available", "page", "page_size", "sort"},
        "/restaurants": {"search", "location", "active", "page", "page_size", "sort"},
        "/deliveries": {"status", "driver_id", "order_id", "sort"},
        "/drivers": {"is_available", "sort"},
    }
    for path, names in required.items():
        operation = document["paths"][path]["get"]
        assert names <= {parameter["name"] for parameter in operation["parameters"]}
        if path in ("/products", "/restaurants"):
            assert not operation.get("security")
        else:
            assert operation["security"] == [{"HTTPBearer": []}]
        for status in ("401", "403", "404", "409", "422", "500"):
            assert operation["responses"][status]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")
    schemas = document["components"]["schemas"]
    assert {"items", "page", "page_size", "total", "total_pages"} <= schemas["OrderPage"]["properties"].keys()
    ids = [op["operationId"] for methods in document["paths"].values() for method, op in methods.items()
           if method in ("get", "post", "patch", "delete")]
    assert len(ids) == len(set(ids))
    # All local schema references resolve.
    def check_refs(value):
        if isinstance(value, dict):
            if "$ref" in value and value["$ref"].startswith("#/components/schemas/"):
                assert value["$ref"].split("/")[-1] in schemas
            for child in value.values():
                check_refs(child)
        elif isinstance(value, list):
            for child in value:
                check_refs(child)
    check_refs(document)
