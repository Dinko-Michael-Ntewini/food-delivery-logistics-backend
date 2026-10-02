"""Focused regression checks for integrity issues found in the pre-Stage-6 audit."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.enums import UserRole
from app.core.security import create_access_token, hash_password
from app.models.identity import User


def user(db, email, role):
    result = User(email=email, password_hash=hash_password("password123"),
                  full_name=email, role=role, is_active=True)
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


def auth(account):
    return {"Authorization": f"Bearer {create_access_token(account.id)}"}


def test_default_address_switch_on_patch(client, db_session):
    customer = user(db_session, "address-audit@example.com", UserRole.CUSTOMER)
    headers = auth(customer)
    payload = {"label": "Home", "recipient_name": "A", "recipient_phone": "123",
               "line1": "1 Street", "city": "Accra", "is_default": True}
    first = client.post("/customers/me/addresses", json=payload, headers=headers)
    assert first.status_code == 201
    payload.update(label="Office", line1="2 Street", is_default=False)
    second = client.post("/customers/me/addresses", json=payload, headers=headers)
    assert second.status_code == 201
    change = client.patch(f"/customers/me/addresses/{second.json()['id']}",
                          json={"is_default": True}, headers=headers)
    assert change.status_code == 200
    rows = client.get("/customers/me/addresses", headers=headers).json()
    assert [row["id"] for row in rows if row["is_default"]] == [second.json()["id"]]


def test_staff_scope_final_owner_and_variant_update(client, db_session):
    owner = user(db_session, "owner-audit@example.com", UserRole.RESTAURANT_OWNER)
    staff = user(db_session, "staff-audit@example.com", UserRole.STAFF)
    unrelated = user(db_session, "unrelated-audit@example.com", UserRole.RESTAURANT_OWNER)
    rid = client.post("/restaurants", json={"name": "Audit", "slug": "audit"},
                      headers=auth(owner)).json()["id"]
    assert client.post("/restaurants", json={"name": "Duplicate", "slug": "audit"},
                       headers=auth(owner)).status_code == 409
    owner_membership = client.get(f"/restaurants/{rid}/staff", headers=auth(owner)).json()[0]["id"]
    assert client.patch(f"/restaurants/{rid}/staff/{owner_membership}",
                        json={"is_active": False}, headers=auth(owner)).status_code == 409
    assert client.patch(f"/restaurants/{rid}/staff/{owner_membership}",
                        json={"staff_role": "STAFF"}, headers=auth(owner)).status_code == 409
    assert client.delete(f"/restaurants/{rid}/staff/{owner_membership}",
                         headers=auth(unrelated)).status_code == 403
    branch = client.post(f"/restaurants/{rid}/branches", json={"name": "Main", "line1": "1", "city": "Accra"},
                         headers=auth(owner)).json()
    assert client.post(f"/restaurants/{rid}/staff", json={"user_id": str(staff.id), "staff_role": "OWNER"},
                       headers=auth(owner)).status_code == 422
    membership = client.post(f"/restaurants/{rid}/staff", json={"user_id": str(staff.id),
                              "staff_role": "MANAGER", "branch_id": branch["id"]}, headers=auth(owner))
    assert membership.status_code == 201
    assert client.patch(f"/restaurants/{rid}", json={"name": "No"}, headers=auth(staff)).status_code == 403
    assert client.post(f"/restaurants/{rid}/menus", json={"name": "No"}, headers=auth(staff)).status_code == 403
    menu = client.post(f"/restaurants/{rid}/menus", json={"name": "Lunch"}, headers=auth(owner)).json()
    category = client.post(f"/menus/{menu['id']}/categories", json={"name": "Meals"}, headers=auth(owner)).json()
    product = client.post(f"/categories/{category['id']}/products", json={"name": "Rice", "base_price": "10.00"},
                          headers=auth(owner)).json()
    variant = client.post(f"/products/{product['id']}/variants", json={"name": "Large", "price_delta": "2.00"},
                          headers=auth(owner)).json()
    assert client.patch(f"/variants/{variant['id']}", json={"is_available": False}, headers=auth(owner)).status_code == 200
    assert client.patch(f"/variants/{variant['id']}", json={"price_override": "15.00"},
                        headers=auth(owner)).status_code == 422
    assert client.patch(f"/variants/{variant['id']}", json={"price_delta": None, "price_override": "15.00"},
                        headers=auth(owner)).status_code == 200
    assert client.get("/menus/not-a-uuid/categories").status_code == 422
    assert client.get("/products/search", params={"min_price": "-1"}).status_code == 422
    assert client.get("/products/search", params={"sort": "not_allowed"}).status_code == 422
    assert client.get("/restaurants", params={"sort": "not_allowed"}).status_code == 422


def test_jwt_expiration_required_and_password_not_exposed(client, db_session):
    account = user(db_session, "jwt-audit@example.com", UserRole.CUSTOMER)
    secret = get_settings().secret_key
    missing_exp = jwt.encode({"sub": str(account.id)}, secret, algorithm="HS256")
    expired = jwt.encode({"sub": str(account.id), "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
                         secret, algorithm="HS256")
    for token in (missing_exp, expired, "malformed"):
        assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    response = client.get("/auth/me", headers=auth(account))
    assert response.status_code == 200
    assert "password_hash" not in response.json()


def test_fresh_application_integrated_stage_3_to_5_flow(client, db_session):
    """The fixture creates an empty database for this independent whole-app flow."""
    owner = user(db_session, "flow-owner@example.com", UserRole.RESTAURANT_OWNER)
    login = client.post("/auth/login", json={"email": owner.email, "password": "password123"})
    assert login.status_code == 200
    owner_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    restaurant = client.post("/restaurants", json={"name": "Flow Food", "slug": "flow-food"}, headers=owner_headers)
    assert restaurant.status_code == 201
    rid = restaurant.json()["id"]
    branch = client.post(f"/restaurants/{rid}/branches", json={"name": "Main", "line1": "1 Road", "city": "Accra"}, headers=owner_headers)
    assert branch.status_code == 201
    alternate = client.post(f"/restaurants/{rid}/branches", json={"name": "Other", "line1": "2 Road", "city": "Accra"}, headers=owner_headers)
    assert alternate.status_code == 201
    menu = client.post(f"/restaurants/{rid}/menus", json={"name": "Dinner"}, headers=owner_headers)
    assert menu.status_code == 201
    category = client.post(f"/menus/{menu.json()['id']}/categories", json={"name": "Mains"}, headers=owner_headers)
    assert category.status_code == 201
    product = client.post(f"/categories/{category.json()['id']}/products", json={"name": "Stew", "base_price": "12.25"}, headers=owner_headers)
    assert product.status_code == 201
    direct_product = client.post("/products", json={"category_id": category.json()["id"], "name": "Soup", "base_price": "5.50"}, headers=owner_headers)
    assert direct_product.status_code == 201
    assert client.get("/products", params={"restaurant_id": rid, "search": "Soup"}).json()["total"] == 1
    variant = client.post(f"/products/{product.json()['id']}/variants", json={"name": "Large", "price_delta": "2.50"}, headers=owner_headers)
    assert variant.status_code == 201
    foreign = client.post("/restaurants", json={"name": "Other Food", "slug": "other-food"}, headers=owner_headers)
    foreign_menu = client.post(f"/restaurants/{foreign.json()['id']}/menus", json={"name": "Dinner"}, headers=owner_headers)
    foreign_category = client.post(f"/menus/{foreign_menu.json()['id']}/categories", json={"name": "Mains"}, headers=owner_headers)
    foreign_product = client.post(f"/categories/{foreign_category.json()['id']}/products", json={"name": "Foreign", "base_price": "8.00"}, headers=owner_headers)
    assert foreign_product.status_code == 201
    registered = client.post("/auth/register", json={"email": "flow-customer@example.com", "password": "password123", "full_name": "Flow Customer"})
    assert registered.status_code == 201
    customer_login = client.post("/auth/login", json={"email": "flow-customer@example.com", "password": "password123"})
    customer_headers = {"Authorization": f"Bearer {customer_login.json()['access_token']}"}
    assert client.patch("/customers/me/profile", json={"marketing_opt_in": True}, headers=customer_headers).status_code == 200
    assert client.get("/customers/me/profile", headers=customer_headers).json()["marketing_opt_in"] is True
    address = client.post("/customers/me/addresses", json={"label": "Home", "recipient_name": "Customer", "recipient_phone": "123", "line1": "3 Road", "city": "Accra", "is_default": True}, headers=customer_headers)
    assert address.status_code == 201 and address.json()["is_default"] is True
    empty = client.get("/cart", headers=customer_headers)
    assert empty.status_code == 200 and empty.json()["branch_id"] is None
    payload = {"product_id": product.json()["id"], "quantity": 1, "branch_id": branch.json()["id"]}
    plain = client.post("/cart/items", json=payload, headers=customer_headers)
    assert plain.status_code == 201 and plain.json()["subtotal"] == "12.25"
    variant_payload = {"product_id": product.json()["id"], "product_variant_id": variant.json()["id"], "quantity": 1}
    with_variant = client.post("/cart/items", json=variant_payload, headers=customer_headers)
    assert with_variant.status_code == 201 and with_variant.json()["subtotal"] == "27.00"
    duplicate = client.post("/cart/items", json=variant_payload, headers=customer_headers)
    assert duplicate.status_code == 201 and len(duplicate.json()["items"]) == 2
    assert duplicate.json()["subtotal"] == "41.75"
    first_id = next(row["id"] for row in duplicate.json()["items"] if row["product_variant_id"] is None)
    updated = client.patch(f"/cart/items/{first_id}", json={"quantity": 2}, headers=customer_headers)
    assert updated.status_code == 200 and updated.json()["subtotal"] == "54.00"
    assert client.post("/cart/items", json={**payload, "branch_id": alternate.json()["id"]}, headers=customer_headers).status_code == 409
    assert client.post("/cart/items", json={"product_id": foreign_product.json()["id"], "quantity": 1}, headers=customer_headers).status_code == 409
    second = client.post("/auth/register", json={"email": "flow-second@example.com", "password": "password123", "full_name": "Other Customer"})
    assert second.status_code == 201
    second_login = client.post("/auth/login", json={"email": "flow-second@example.com", "password": "password123"})
    second_headers = {"Authorization": f"Bearer {second_login.json()['access_token']}"}
    assert client.patch(f"/cart/items/{first_id}", json={"quantity": 3}, headers=second_headers).status_code == 404
    assert client.delete(f"/cart/items/{first_id}", headers=second_headers).status_code == 404
    for row in updated.json()["items"]:
        assert client.delete(f"/cart/items/{row['id']}", headers=customer_headers).status_code == 204
    assert client.get("/cart", headers=customer_headers).json()["branch_id"] is None


def test_openapi_routes_tags_security_and_response_types(client):
    specification = client.get("/openapi.json")
    assert specification.status_code == 200
    document = specification.json()
    assert document["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    operations = [operation for methods in document["paths"].values()
                  for method, operation in methods.items() if method in {"get", "post", "patch", "delete"}]
    ids = [operation["operationId"] for operation in operations]
    assert len(ids) == len(set(ids))
    assert len(operations) - 2 >= 20
    assert "security" not in document["paths"]["/products/search"]["get"]
    assert "security" not in document["paths"]["/products"]["get"]
    assert document["paths"]["/products"]["post"]["security"] == [{"HTTPBearer": []}]
    assert document["paths"]["/cart"]["get"]["security"] == [{"HTTPBearer": []}]
    assert document["paths"]["/customers/me/addresses"]["post"]["security"] == [{"HTTPBearer": []}]
    assert document["paths"]["/restaurants/{rid}/staff"]["post"]["security"] == [{"HTTPBearer": []}]
    assert document["paths"]["/customers/me/profile"]["get"]["tags"] == ["Customers"]
    assert document["paths"]["/products/search"]["get"]["tags"] == ["Products"]
    assert "password_hash" not in str(document["components"]["schemas"])
    assert client.get("/docs").status_code == 200


def test_production_rejects_example_secret():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production",
                 secret_key="replace-with-a-long-random-secret-before-production")
