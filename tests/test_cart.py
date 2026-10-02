from decimal import Decimal
from uuid import UUID

import pytest

from app.core.enums import UserRole
from app.core.security import create_access_token, hash_password
from app.models.identity import User
from app.models.ordering import CartItem
from app.models.restaurant import (
    Category, Menu, Product, ProductVariant, Restaurant, RestaurantBranch,
)


def headers(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def money(value):
    return Decimal(str(value))


@pytest.fixture()
def catalog(db_session):
    def user(email, role):
        instance = User(email=email, password_hash=hash_password("password123"),
                        full_name=email, role=role, is_active=True)
        db_session.add(instance)
        db_session.flush()
        return instance

    customer = user("cart-customer@example.com", UserRole.CUSTOMER)
    second_customer = user("cart-second@example.com", UserRole.CUSTOMER)
    owner = user("cart-owner@example.com", UserRole.RESTAURANT_OWNER)
    staff = user("cart-staff@example.com", UserRole.STAFF)
    driver = user("cart-driver@example.com", UserRole.DRIVER)

    restaurant = Restaurant(name="Cart Restaurant", slug="cart-restaurant")
    another_restaurant = Restaurant(name="Other Restaurant", slug="other-restaurant")
    db_session.add_all([restaurant, another_restaurant])
    db_session.flush()
    branch = RestaurantBranch(restaurant_id=restaurant.id, name="Main", line1="1 Main", city="Accra")
    other_branch = RestaurantBranch(restaurant_id=restaurant.id, name="Second", line1="2 Main", city="Accra")
    foreign_branch = RestaurantBranch(restaurant_id=another_restaurant.id, name="Foreign", line1="3 Main", city="Accra")
    db_session.add_all([branch, other_branch, foreign_branch])
    db_session.flush()
    menu = Menu(restaurant_id=restaurant.id, name="Dinner")
    foreign_menu = Menu(restaurant_id=another_restaurant.id, name="Dinner")
    db_session.add_all([menu, foreign_menu])
    db_session.flush()
    category = Category(menu_id=menu.id, name="Mains")
    foreign_category = Category(menu_id=foreign_menu.id, name="Mains")
    db_session.add_all([category, foreign_category])
    db_session.flush()
    product = Product(category_id=category.id, name="Rice", base_price=Decimal("12.35"))
    second_product = Product(category_id=category.id, name="Beans", base_price=Decimal("4.10"))
    foreign_product = Product(category_id=foreign_category.id, name="Foreign Rice", base_price=Decimal("8.00"))
    db_session.add_all([product, second_product, foreign_product])
    db_session.flush()
    delta = ProductVariant(product_id=product.id, name="Large", price_delta=Decimal("2.15"))
    override = ProductVariant(product_id=product.id, name="Special", price_override=Decimal("18.75"))
    wrong_variant = ProductVariant(product_id=second_product.id, name="Beans Large")
    db_session.add_all([delta, override, wrong_variant])
    db_session.commit()
    return locals()


def post_item(client, user, product, quantity=1, branch=None, variant=None):
    payload = {"product_id": str(product.id), "quantity": quantity}
    if branch is not None:
        payload["branch_id"] = str(branch.id)
    if variant is not None:
        payload["product_variant_id"] = str(variant.id)
    return client.post("/cart/items", json=payload, headers=headers(user))


def test_empty_cart_and_role_guards(client, catalog):
    customer = catalog["customer"]
    assert client.get("/cart").status_code == 401
    for role in ("owner", "staff", "driver"):
        assert client.get("/cart", headers=headers(catalog[role])).status_code == 403
    result = client.get("/cart", headers=headers(customer))
    assert result.status_code == 200
    assert result.json()["branch_id"] is None
    assert result.json()["items"] == []
    assert money(result.json()["subtotal"]) == Decimal("0.00")
    other = client.get("/cart", headers=headers(catalog["second_customer"]))
    assert other.status_code == 200
    assert other.json()["id"] != result.json()["id"]


def test_first_item_branch_and_validation(client, catalog, db_session):
    c = catalog["customer"]
    p = catalog["product"]
    branch = catalog["branch"]
    assert post_item(client, c, p).status_code == 422
    assert post_item(client, c, p, branch=catalog["foreign_branch"]).status_code == 409
    branch.is_active = False
    db_session.commit()
    assert post_item(client, c, p, branch=branch).status_code == 409
    branch.is_active = True
    db_session.commit()
    assert client.post("/cart/items", json={"product_id": str(p.id), "branch_id": "00000000-0000-0000-0000-000000000001", "quantity": 1}, headers=headers(c)).status_code == 404
    assert client.post("/cart/items", json={"product_id": "00000000-0000-0000-0000-000000000001", "branch_id": str(branch.id), "quantity": 1}, headers=headers(c)).status_code == 404
    assert post_item(client, c, p, branch=branch).status_code == 201
    assert client.get("/cart", headers=headers(c)).json()["branch_id"] == str(branch.id)


def test_product_variant_quantity_and_availability(client, catalog, db_session):
    c = catalog["customer"]
    p = catalog["product"]
    branch = catalog["branch"]
    assert post_item(client, c, p, quantity=0, branch=branch).status_code == 422
    assert post_item(client, c, p, quantity=-1, branch=branch).status_code == 422
    assert post_item(client, c, p, branch=branch, variant=catalog["wrong_variant"]).status_code == 422
    assert client.post("/cart/items", json={"product_id": str(p.id), "product_variant_id": "00000000-0000-0000-0000-000000000001", "branch_id": str(branch.id), "quantity": 1}, headers=headers(c)).status_code == 404
    delta = catalog["delta"]
    delta.is_available = False
    db_session.commit()
    assert post_item(client, c, p, branch=branch, variant=delta).status_code == 409
    delta.is_available = True
    p.is_available = False
    db_session.commit()
    assert post_item(client, c, p, branch=branch).status_code == 409
    p.is_available = True
    p.category.is_active = False
    db_session.commit()
    assert post_item(client, c, p, branch=branch).status_code == 409
    p.category.is_active = True
    db_session.commit()
    assert post_item(client, c, p, branch=branch).status_code == 201
    p.is_available = False
    db_session.commit()
    visible = client.get("/cart", headers=headers(c)).json()["items"]
    assert len(visible) == 1 and visible[0]["product_available"] is False


def test_plain_duplicate_and_existing_variant_availability(client, catalog, db_session):
    customer = catalog["customer"]
    product = catalog["product"]
    branch = catalog["branch"]
    assert post_item(client, customer, product, branch=branch).status_code == 201
    repeated = post_item(client, customer, product, quantity=2)
    assert repeated.status_code == 201
    assert len(repeated.json()["items"]) == 1
    assert repeated.json()["items"][0]["quantity"] == 3
    variant = catalog["delta"]
    assert post_item(client, customer, product, variant=variant).status_code == 201
    variant.is_available = False
    db_session.commit()
    current = client.get("/cart", headers=headers(customer)).json()
    assert len(current["items"]) == 2
    assert next(item for item in current["items"] if item["product_variant_id"])["variant_available"] is False


def test_full_cart_flow_pricing_duplicates_ownership_and_reset(client, catalog, db_session):
    c = catalog["customer"]
    second = catalog["second_customer"]
    p = catalog["product"]
    branch = catalog["branch"]
    ch = headers(c)
    assert client.get("/cart", headers=ch).status_code == 200
    first = post_item(client, c, p, branch=branch)
    assert first.status_code == 201
    assert first.json()["branch_id"] == str(branch.id)
    assert money(first.json()["items"][0]["unit_price"]) == Decimal("12.35")
    assert money(first.json()["items"][0]["line_total"]) == Decimal("12.35")
    assert money(first.json()["subtotal"]) == Decimal("12.35")
    delta = post_item(client, c, p, variant=catalog["delta"])
    assert delta.status_code == 201
    assert money(delta.json()["subtotal"]) == Decimal("26.85")
    assert money(next(i for i in delta.json()["items"] if i["product_variant_id"])["unit_price"]) == Decimal("14.50")
    duplicate = post_item(client, c, p, quantity=2, variant=catalog["delta"], branch=branch)
    assert duplicate.status_code == 201
    assert len(duplicate.json()["items"]) == 2
    assert next(i for i in duplicate.json()["items"] if i["product_variant_id"])["quantity"] == 3
    assert money(next(i for i in duplicate.json()["items"] if i["product_variant_id"])["line_total"]) == Decimal("43.50")
    assert money(duplicate.json()["subtotal"]) == Decimal("55.85")
    override = post_item(client, c, p, variant=catalog["override"])
    assert override.status_code == 201
    assert money(next(i for i in override.json()["items"] if i["variant_name"] == "Special")["unit_price"]) == Decimal("18.75")
    assert money(override.json()["subtotal"]) == Decimal("74.60")
    assert post_item(client, c, catalog["second_product"]).status_code == 201
    assert post_item(client, c, p, branch=catalog["other_branch"]).status_code == 409
    assert post_item(client, c, catalog["foreign_product"]).status_code == 409
    item_id = next(i["id"] for i in override.json()["items"] if i["product_variant_id"] is None)
    assert client.patch(f"/cart/items/{item_id}", json={"quantity": 0}, headers=ch).status_code == 422
    assert client.patch(f"/cart/items/{item_id}", json={"quantity": -1}, headers=ch).status_code == 422
    assert client.patch(f"/cart/items/{item_id}", json={"quantity": 2}, headers=headers(second)).status_code == 404
    assert client.delete(f"/cart/items/{item_id}", headers=headers(second)).status_code == 404
    changed = client.patch(f"/cart/items/{item_id}", json={"quantity": 2}, headers=ch)
    assert changed.status_code == 200
    assert money(next(i for i in changed.json()["items"] if i["id"] == item_id)["line_total"]) == Decimal("24.70")
    assert money(changed.json()["subtotal"]) == Decimal("91.05")
    assert db_session.query(CartItem).filter(CartItem.cart_id == UUID(changed.json()["id"])).count() == 4
    for item in changed.json()["items"]:
        assert client.delete(f"/cart/items/{item['id']}", headers=ch).status_code == 204
    empty = client.get("/cart", headers=ch).json()
    assert empty["items"] == [] and empty["branch_id"] is None
    assert post_item(client, c, p).status_code == 422
    assert post_item(client, c, p, branch=branch).status_code == 201
