"""Stage 9 filters, deterministic ordering, metadata, query safety and RBAC."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event

from app.models.ordering import Order
from app.models.restaurant import Product, RestaurantBranch
from test_orders import auth, order_setup  # noqa: F401
from test_deliveries import create_delivery, create_driver, assign, second_driver


@pytest.fixture()
def catalogue(order_setup, db_session):
    data = order_setup
    data["restaurant"].name = "Alpha Kitchen"
    data["foreign_restaurant"].name = "Zulu Kitchen"
    data["other_branch"].city = "Accra"
    products = [Product(category_id=data["category"].id, name="Rice Deluxe", base_price=Decimal("20.00")),
                Product(category_id=data["category"].id, name="Rice Budget", base_price=Decimal("5.00")),
                Product(category_id=data["category"].id, name="Rice Offline", base_price=Decimal("8.00"),
                        is_available=False)]
    db_session.add_all(products)
    db_session.commit()
    return data


def test_product_combined_filters_decimal_bounds_and_availability(client, catalogue):
    data = catalogue
    params = {"search": "rIcE", "category_id": str(data["category"].id),
              "restaurant_id": str(data["restaurant"].id), "min_price": "12.35", "max_price": "20.00",
              "available": True, "sort": "price"}
    response = client.get("/products/search", params=params)
    assert response.status_code == 200
    body = response.json()
    assert [Decimal(row["base_price"]) for row in body["items"]] == [Decimal("12.35"), Decimal("20.00")]
    assert body["total"] == 2 and body["total_pages"] == 1
    assert len({row["id"] for row in body["items"]}) == 2
    assert client.get("/products", params={"min_price": "20.00"}).json()["total"] == 1
    assert client.get("/products", params={"max_price": "5.00"}).json()["total"] == 1
    offline = client.get("/products", params={"available": False}).json()
    assert offline["total"] == 1 and offline["items"][0]["name"] == "Rice Offline"
    assert client.get("/products", params={"restaurant_id": str(data["foreign_restaurant"].id)}).json()["total"] == 1


def test_product_pagination_sorting_and_empty_metadata(client, catalogue):
    params = {"restaurant_id": str(catalogue["restaurant"].id), "page_size": 1, "sort": "price"}
    pages = [client.get("/products", params={**params, "page": page}).json() for page in (1, 2, 3)]
    assert [Decimal(page["items"][0]["base_price"]) for page in pages] == [Decimal("5.00"), Decimal("12.35"), Decimal("20.00")]
    assert all(page["total"] == 3 and page["total_pages"] == 3 for page in pages)
    assert len({page["items"][0]["id"] for page in pages}) == 3
    descending = client.get("/products", params={**params, "page_size": 100, "sort": "-price"}).json()
    assert [row["id"] for row in descending["items"]] == [page["items"][0]["id"] for page in reversed(pages)]
    assert client.get("/products", params={**params, "page": 4}).json()["items"] == []
    empty = client.get("/products", params={"search": "absent"}).json()
    assert empty == {"items": [], "page": 1, "page_size": 20, "total": 0, "total_pages": 0}
    # Identical primary sort values still yield stable ID order.
    repeat = client.get("/products", params={"sort": "created_at"}).json()
    assert repeat == client.get("/products", params={"sort": "created_at"}).json()


def test_product_query_validation(client, catalogue):
    for params in ({"min_price": "-0.01"}, {"max_price": "-1"}, {"min_price": "21", "max_price": "20"},
                   {"category_id": "bad"}, {"restaurant_id": "bad"}, {"sort": "price; DROP TABLE products"},
                   {"page": 0}, {"page_size": 0}, {"page_size": 101}, {"min_price": "NaN"}):
        response = client.get("/products/search", params=params)
        assert response.status_code == 422, (params, response.text)
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_restaurant_combined_location_filters_no_duplicate_rows(client, catalogue, db_session):
    data = catalogue
    combined = client.get("/restaurants", params={"search": "kitchen", "location": "accra", "active": True}).json()
    assert combined["total"] == 2
    assert len({row["id"] for row in combined["items"]}) == 2
    assert client.get("/restaurants", params={"search": "alpha", "location": "accra"}).json()["total"] == 1
    data["foreign_restaurant"].is_active = False
    db_session.commit()
    body = client.get("/restaurants", params={"search": "zulu", "location": "accra", "active": False}).json()
    assert body["total"] == 1 and body["items"][0]["id"] == str(data["foreign_restaurant"].id)


def test_restaurant_sorting_metadata_and_validation(client, catalogue):
    ascending = client.get("/restaurants", params={"sort": "name", "page_size": 1}).json()
    descending = client.get("/restaurants", params={"sort": "-name", "page_size": 1}).json()
    assert ascending["items"][0]["name"] == "Alpha Kitchen"
    assert descending["items"][0]["name"] == "Zulu Kitchen"
    assert ascending["total"] == 2 and ascending["total_pages"] == 2
    assert client.get("/restaurants", params={"page": 3, "page_size": 1}).json()["items"] == []
    empty = client.get("/restaurants", params={"location": "nowhere"}).json()
    assert empty["total"] == empty["total_pages"] == 0 and empty["items"] == []
    for params in ({"page": -1}, {"page_size": 0}, {"page_size": 101}, {"sort": "slug"}):
        assert client.get("/restaurants", params=params).status_code == 422


@pytest.fixture()
def orders(client, order_setup, db_session):
    data = order_setup
    rows = []
    for index, (customer, address, branch, product, quantity) in enumerate([
        (data["customer"], data["address"], data["branch"], data["product"], 1),
        (data["customer"], data["address"], data["other_branch"], data["product"], 2),
        (data["other_customer"], data["foreign_address"], data["branch"], data["product"], 3),
        (data["other_customer"], data["foreign_address"], data["foreign_branch"], data["foreign_product"], 4),
    ], start=1):
        assert client.post("/cart/items", json={"product_id": str(product.id), "branch_id": str(branch.id),
                                                "quantity": quantity}, headers=auth(customer)).status_code == 201
        response = client.post("/orders/checkout", json={"address_id": str(address.id),
                                                        "payment_method": "MOBILE_MONEY"}, headers=auth(customer))
        assert response.status_code == 201
        if index % 2 == 0:
            assert client.patch(f"/orders/{response.json()['id']}/status", json={"status": "CONFIRMED"},
                                headers=auth(data["admin"])).status_code == 200
        row = db_session.get(Order, UUID(response.json()["id"]))
        row.placed_at = datetime(2026, 1, index, 12, tzinfo=timezone.utc)
        rows.append(row)
    db_session.commit()
    return data, rows


def test_order_combined_filters_dates_and_admin_customer_filter(client, orders):
    data, rows = orders
    header = auth(data["admin"])
    params = {"restaurant_id": str(data["restaurant"].id), "branch_id": str(data["other_branch"].id),
              "status": "CONFIRMED", "date_from": "2026-01-02T12:00:00Z", "date_to": "2026-01-02T12:00:00Z"}
    result = client.get("/orders", params=params, headers=header).json()
    assert result["total"] == 1 and result["items"][0]["id"] == str(rows[1].id)
    assert client.get("/orders", params={"customer_id": str(rows[0].customer_id)}, headers=header).json()["total"] == 2
    assert client.get("/orders", params={"search": rows[2].order_number.lower()}, headers=header).json()["total"] == 1
    assert client.get("/orders", params={"date_from": "2026-01-02T14:00:00+02:00",
                                        "date_to": "2026-01-02T12:00:00"}, headers=header).json()["total"] == 1


def test_order_filter_rbac_customer_restaurant_and_branch_isolation(client, orders):
    data, rows = orders
    assert client.get("/orders", headers=auth(data["customer"])).json()["total"] == 2
    assert client.get("/orders", params={"restaurant_id": str(data["foreign_restaurant"].id)},
                      headers=auth(data["customer"])).json()["total"] == 0
    assert client.get("/orders", params={"search": rows[2].order_number},
                      headers=auth(data["customer"])).json()["total"] == 0
    for actor in ("owner", "staff"):
        assert client.get("/orders", params={"restaurant_id": str(data["foreign_restaurant"].id)},
                          headers=auth(data[actor])).json()["total"] == 0
    assert client.get("/orders", params={"branch_id": str(data["other_branch"].id)},
                      headers=auth(data["staff"])).json()["total"] == 0
    assert client.get("/orders", headers=auth(data["owner"])).json()["total"] == 3
    assert client.get("/orders", params={"restaurant_id": str(data["foreign_restaurant"].id)},
                      headers=auth(data["admin"])).json()["total"] == 1
    for actor in ("customer", "owner", "staff"):
        assert client.get("/orders", params={"customer_id": str(rows[2].customer_id)},
                          headers=auth(data[actor])).status_code == 403


def test_order_pagination_sorting_and_empty_results(client, orders):
    data, rows = orders
    header = auth(data["admin"])
    pages = [client.get("/orders", params={"sort": "placed_at", "page_size": 2, "page": page},
                        headers=header).json() for page in (1, 2)]
    assert [item["id"] for page in pages for item in page["items"]] == [str(row.id) for row in rows]
    assert all(page["total"] == 4 and page["total_pages"] == 2 for page in pages)
    for sort in ("total", "status", "created_at", "updated_at", "placed_at"):
        asc = client.get("/orders", params={"sort": sort}, headers=header).json()
        desc = client.get("/orders", params={"sort": "-" + sort}, headers=header).json()
        assert [item["id"] for item in asc["items"]] == [item["id"] for item in reversed(desc["items"])]
    empty = client.get("/orders", params={"branch_id": str(uuid4())}, headers=header).json()
    assert empty["items"] == [] and empty["total"] == empty["total_pages"] == 0
    assert client.get("/orders", params={"page": 3, "page_size": 2}, headers=header).json()["items"] == []


def test_order_invalid_filters_are_normalized(client, orders):
    data, _ = orders
    for params in ({"status": "bad"}, {"restaurant_id": "bad"}, {"branch_id": "bad"}, {"customer_id": "bad"},
                   {"date_from": "not-a-date"}, {"date_from": "2026-02-01", "date_to": "2026-01-01"},
                   {"sort": "total DESC; SELECT 1"}, {"page": 0}, {"page_size": 101}):
        response = client.get("/orders", params=params, headers=auth(data["admin"]))
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_order_list_batches_related_data_instead_of_per_order_queries(client, orders, db_session):
    data, _ = orders
    headers = auth(data["admin"])
    db_session.expire_all()
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)
    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get("/orders", headers=headers)
        assert response.status_code == 200 and response.json()["total"] == 4
        assert len(statements) <= 10, len(statements)
    finally:
        event.remove(engine, "before_cursor_execute", capture)


def test_delivery_and_driver_filters_preserve_scope_and_list_shapes(client, order_setup, db_session):
    data = order_setup
    first, second = create_delivery(client, data), create_delivery(client, data)
    driver = create_driver(client, data)
    other_user = second_driver(db_session)
    other_driver = create_driver(client, data, other_user, is_available=False, vehicle_type="car")
    assert assign(client, data, first, driver).status_code == 200
    params = {"status": "ASSIGNED", "driver_id": driver["id"], "order_id": first["order_id"], "sort": "-created_at"}
    response = client.get("/deliveries", params=params, headers=auth(data["customer"]))
    assert response.status_code == 200 and [item["id"] for item in response.json()] == [first["id"]]
    assert client.get("/deliveries", params=params, headers=auth(data["other_customer"])).json() == []
    assert client.get("/deliveries", params={"order_id": second["order_id"]}, headers=auth(data["driver"])).json() == []
    assert client.get("/drivers", params={"is_available": False}, headers=auth(data["admin"])).json()[0]["id"] == other_driver["id"]
    for path, params in (("/deliveries", {"driver_id": "bad"}), ("/deliveries", {"status": "bad"}),
                         ("/deliveries", {"sort": "order_id"}), ("/drivers", {"sort": "user_id"})):
        assert client.get(path, params=params, headers=auth(data["admin"])).status_code == 422
