"""Final evidence from the migration-built schema and a full realistic API workflow."""
import io
import json
import re
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import Numeric, Uuid, create_engine, inspect, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import configure_mappers, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateIndex, CreateTable

from app import models
from app.core.config import get_settings
from app.core.enums import UserRole
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import configure_sqlite, get_db
from app.main import app
from app.models.identity import User
from app.models.payment import Payment

ROOT = Path(__file__).resolve().parents[1]
ENTITIES = {"User", "Address", "CustomerProfile", "Restaurant", "RestaurantBranch", "RestaurantStaff",
            "Menu", "Category", "Product", "ProductVariant", "Cart", "CartItem", "Order", "OrderItem",
            "OrderStatusHistory", "Payment", "Refund", "Driver", "Delivery", "DeliveryStatusHistory"}


def test_final_models_relationships_and_postgresql_ddl_compile():
    configure_mappers()
    assert {mapper.class_.__name__ for mapper in Base.registry.mappers} == ENTITIES
    assert len(Base.metadata.tables) == 20
    for table in Base.metadata.tables.values():
        assert isinstance(table.c.id.type, Uuid) and table.c.id.primary_key
        assert not table.c.created_at.nullable
        if table.name not in {"order_items", "order_status_history", "delivery_status_history"}:
            assert "updated_at" in table.c
        if table.name not in {"users", "restaurants"}:
            assert table.foreign_keys
        assert str(CreateTable(table).compile(dialect=postgresql.dialect()))
        for index in table.indexes:
            assert str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    for cls, field in ((models.CustomerProfile, "user_id"), (models.Driver, "user_id"),
                       (models.Delivery, "order_id")):
        assert cls.__table__.c[field].unique
    for cls, relation in ((models.User, "customer_profile"), (models.User, "driver_profile"),
                          (models.Order, "delivery")):
        assert inspect(cls).relationships[relation].uselist is False
    for cls, relation in ((models.User, "addresses"), (models.Restaurant, "branches"),
                          (models.Restaurant, "staff_memberships"), (models.CustomerProfile, "orders"),
                          (models.Restaurant, "menus"), (models.Menu, "categories"),
                          (models.Category, "products"), (models.Product, "variants"),
                          (models.Cart, "items"), (models.Order, "items"),
                          (models.Order, "status_history"), (models.Order, "payments"),
                          (models.Payment, "refunds"), (models.Driver, "deliveries"),
                          (models.Delivery, "status_history")):
        assert inspect(cls).relationships[relation].uselist
    assert inspect(models.User).relationships["restaurant_memberships"].mapper.class_ == models.RestaurantStaff
    assert inspect(models.Restaurant).relationships["staff_memberships"].mapper.class_ == models.RestaurantStaff
    for cls, fields in ((models.Product, ["base_price"]), (models.ProductVariant, ["price_delta", "price_override"]),
                       (models.Order, ["subtotal", "delivery_fee", "total_amount"]),
                       (models.OrderItem, ["unit_price", "line_total"]),
                       (models.Payment, ["amount"]), (models.Refund, ["amount"])):
        assert all(isinstance(cls.__table__.c[field].type, Numeric) for field in fields)
    scripts = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    assert scripts.get_heads() == ["c5b21d4e8f32"]
    revisions = list(scripts.walk_revisions())
    assert len({revision.revision for revision in revisions}) == len(revisions) == 6


@pytest.fixture()
def migrated_system(monkeypatch):
    """Real zero-to-head migrations, not metadata.create_all; no developer DB touched."""
    monkeypatch.setenv("SECRET_KEY", "final-system-test-secret-that-is-long-enough")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    get_settings.cache_clear()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    configure_sqlite(engine)
    config = Config(str(ROOT / "alembic.ini"), stdout=io.StringIO())
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        command.check(config)
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "c5b21d4e8f32"
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
        connection.commit()
    assert set(inspect(engine).get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    def override_db():
        try:
            yield session
        except Exception:
            session.rollback()
            raise
    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield client, session
    finally:
        app.dependency_overrides.clear()
        session.close()
        engine.dispose()
        get_settings.cache_clear()


def test_fresh_migrations_full_customer_to_delivered_workflow(migrated_system):
    client, db = migrated_system
    users = {}
    for key, role in (("admin", UserRole.ADMIN), ("owner", UserRole.RESTAURANT_OWNER),
                      ("staff", UserRole.STAFF), ("driver", UserRole.DRIVER),
                      ("other_owner", UserRole.RESTAURANT_OWNER), ("other_driver", UserRole.DRIVER)):
        user = User(email=f"final-{key}@example.com", full_name=key, role=role,
                    password_hash=hash_password("final-test-password"), is_active=True)
        db.add(user)
        users[key] = user
    db.commit()
    def login(email, password="final-test-password"):
        response = client.post("/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200, response.text
        return {"Authorization": "Bearer " + response.json()["access_token"]}
    headers = {key: login(user.email) for key, user in users.items()}
    def call(method, path, *, actor="owner", body=None, status=200):
        response = client.request(method, path, json=body, headers=headers[actor])
        assert response.status_code == status, response.text
        return response.json() if response.content else None
    restaurant = call("POST", "/restaurants", body={"name": "Final Kitchen", "slug": "final-kitchen"}, status=201)
    rid = restaurant["id"]
    branch = call("POST", f"/restaurants/{rid}/branches", body={"name": "Main", "line1": "1 Street", "city": "Accra"}, status=201)
    call("POST", f"/restaurants/{rid}/staff", body={"user_id": str(users["staff"].id), "branch_id": branch["id"],
                                                    "staff_role": "STAFF"}, status=201)
    menu = call("POST", f"/restaurants/{rid}/menus", body={"name": "Lunch"}, status=201)
    category = call("POST", f"/menus/{menu['id']}/categories", body={"name": "Meals"}, status=201)
    product = call("POST", "/products", body={"category_id": category["id"], "name": "Jollof", "base_price": "20.00"}, status=201)
    variant = call("POST", f"/products/{product['id']}/variants", body={"name": "Large", "price_delta": "5.00"}, status=201)
    for key in ("customer", "other_customer"):
        response = client.post("/auth/register", json={"email": f"final-{key}@example.com", "password": "final-test-password",
                                                       "full_name": key})
        assert response.status_code == 201 and "password_hash" not in response.text
        headers[key] = login(f"final-{key}@example.com")
    call("PATCH", "/customers/me/profile", actor="customer", body={"preferred_contact_method": "PHONE", "marketing_opt_in": False})
    address = call("POST", "/customers/me/addresses", actor="customer", body={"label": "Home", "recipient_name": "Customer",
                        "recipient_phone": "123", "line1": "2 Street", "city": "Accra", "is_default": True}, status=201)
    call("GET", "/cart", actor="customer")
    cart = call("POST", "/cart/items", actor="customer", body={"product_id": product["id"], "branch_id": branch["id"],
                      "product_variant_id": variant["id"], "quantity": 2}, status=201)
    assert Decimal(cart["subtotal"]) == Decimal("50.00")
    order = call("POST", "/orders", actor="customer", body={"address_id": address["id"], "payment_method": "MOBILE_MONEY"}, status=201)
    oid = order["id"]
    payment = call("POST", "/payments", actor="customer", body={"order_id": oid})
    assert payment["status"] == "PENDING" and Decimal(payment["amount"]) == Decimal("50.00")
    assert call("POST", "/payments", actor="customer", body={"order_id": oid})["id"] == payment["id"]
    assert len(db.scalars(select(Payment)).all()) == 1
    call("POST", "/payments", actor="other_customer", body={"order_id": oid}, status=404)
    call("POST", "/payments", actor="owner", body={"order_id": oid}, status=403)
    call("POST", "/payments", actor="customer", body={"order_id": oid, "amount": "0.01"}, status=422)
    captured = call("POST", f"/payments/{payment['id']}/confirm", actor="admin")
    call("DELETE", f"/customers/me/addresses/{address['id']}", actor="customer", status=409)
    for target in ("CONFIRMED", "PREPARING", "READY_FOR_PICKUP"):
        call("PATCH", f"/orders/{oid}/status", actor="staff", body={"status": target})
    delivery = call("POST", f"/orders/{oid}/delivery", body={}, status=201)
    driver = call("POST", "/drivers", actor="admin", body={"user_id": str(users["driver"].id), "vehicle_type": "bike"}, status=201)
    call("POST", "/drivers", actor="admin", body={"user_id": str(users["other_driver"].id), "vehicle_type": "bike"}, status=201)
    call("POST", f"/deliveries/{delivery['id']}/assign-driver", body={"driver_id": driver["id"]})
    for target, expected in (("PICKED_UP", "OUT_FOR_DELIVERY"), ("IN_TRANSIT", "OUT_FOR_DELIVERY"), ("DELIVERED", "DELIVERED")):
        call("PATCH", f"/deliveries/{delivery['id']}/status", actor="driver", body={"status": target})
        assert call("GET", f"/orders/{oid}", actor="customer")["status"] == expected
    call("PATCH", f"/deliveries/{delivery['id']}/status", actor="driver", body={"status": "DELIVERED"}, status=409)
    call("PATCH", f"/deliveries/{delivery['id']}/status", actor="other_driver", body={"status": "DELIVERED"}, status=404)
    for actor in ("other_customer", "other_owner"):
        call("GET", f"/deliveries/{delivery['id']}", actor=actor, status=404)
        call("GET", f"/orders/{oid}", actor=actor, status=404)
    assert call("GET", f"/payments/{payment['id']}", actor="customer") == captured
    call("PATCH", f"/products/{product['id']}", body={"name": "New name", "base_price": "99.00"})
    call("PATCH", f"/customers/me/addresses/{address['id']}", actor="customer", body={"line1": "New address"})
    final = call("GET", f"/orders/{oid}", actor="customer")
    assert final["items"] == order["items"] and final["delivery_address_snapshot"] == order["delivery_address_snapshot"]
    assert [row["to_status"] for row in final["status_history"]] == ["PENDING", "CONFIRMED", "PREPARING", "READY_FOR_PICKUP", "OUT_FOR_DELIVERY", "DELIVERED"]
    history = call("GET", f"/deliveries/{delivery['id']}/status-history", actor="driver")
    assert [row["to_status"] for row in history] == ["UNASSIGNED", "ASSIGNED", "PICKED_UP", "IN_TRANSIT", "DELIVERED"]
    assert call("GET", "/cart", actor="customer")["items"] == []
    assert db.execute(text("PRAGMA foreign_key_check")).all() == []


def test_postman_artifacts_cover_openapi_and_use_schema_valid_examples():
    from pydantic import BaseModel
    from app.schemas import auth, cart, customer, delivery, driver, order, payment, product, restaurant
    request_models = {cls.__name__: cls for module in (auth, cart, customer, delivery, driver, order, payment, product, restaurant)
                      for cls in vars(module).values() if isinstance(cls, type) and issubclass(cls, BaseModel)}
    collection = json.loads((ROOT / "postman/Food_Delivery_Logistics_API.postman_collection.json").read_text(encoding="utf-8"))
    environment = json.loads((ROOT / "postman/Food_Delivery_Local.postman_environment.json").read_text(encoding="utf-8"))
    assert collection["info"]["schema"] == "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    assert environment["_postman_variable_scope"] == "environment"
    assert next(row["value"] for row in environment["values"] if row["key"] == "base_url") == "http://127.0.0.1:8000"
    assert all(not row["value"] for row in environment["values"] if "token" in row["key"] or row["key"].endswith("_id") or "password" in row["key"])
    document = app.openapi()
    variables = {row["key"] for row in environment["values"]}
    expected = {(method.upper(), path) for path, methods in document["paths"].items()
                for method in methods if method in ("get", "post", "patch", "delete")}
    seen = set()
    # Validate each JSON example against its actual Pydantic-generated OpenAPI schema.
    assert isinstance(collection["info"]["name"], str) and collection["info"]["name"]
    for folder in collection["item"]:
        for item in folder["item"]:
            request = item["request"]
            assert isinstance(item["name"], str) and isinstance(request["url"]["raw"], str)
            assert request["url"]["raw"].startswith("{{base_url}}/") or request["url"]["raw"] == "{{base_url}}"
            path = request["description"].split("OpenAPI: ", 1)[1].splitlines()[0]
            raw_url = request["url"]["raw"]
            actual_path = raw_url.removeprefix("{{base_url}}").split("?", 1)[0] or "/"
            normalized_path = re.sub(r"\{\{[^}]+\}\}", "{id}", actual_path)
            assert normalized_path == re.sub(r"\{[^}]+\}", "{id}", path)
            referenced = re.findall(r"\{\{([^}]+)\}\}", json.dumps(request))
            assert set(referenced) <= variables
            pair = (request["method"], path)
            assert pair in expected
            seen.add(pair)
            operation = document["paths"][path][request["method"].lower()]
            assert request["auth"]["type"] == ("bearer" if operation.get("security") else "noauth")
            if "body" in request:
                body = json.loads(request["body"]["raw"])
                # Resolve UUID placeholders and leave string examples symbolic without real secrets.
                def replace(value):
                    if isinstance(value, dict):
                        return {key: replace(child) for key, child in value.items()}
                    if isinstance(value, str) and value.startswith("{{"):
                        if value.endswith("_id}}"):
                            return str(uuid4())
                        return "safe@example.com" if "email" in value else "safe-example-value"
                    return value
                schema = operation["requestBody"]["content"]["application/json"]["schema"]
                request_models[schema["$ref"].split("/")[-1]].model_validate(replace(body))
    assert seen == expected
    assert len(collection["item"]) == 17
