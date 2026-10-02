"""Original route contract and backward-compatible query names from the brief."""
import re

from app.main import app
from test_advanced_api import catalogue, orders  # noqa: F401
from test_orders import auth, order_setup  # noqa: F401


def test_original_twenty_core_routes():
    normalize = lambda path: re.sub(r"\{[^}]+\}", "{id}", path)
    actual = {(method.upper(), normalize(path)) for path, methods in app.openapi()["paths"].items()
              for method in methods if method in {"get", "post", "patch", "delete"}}
    required = {
        ("POST", "/auth/register"), ("POST", "/auth/login"), ("GET", "/auth/me"),
        ("POST", "/restaurants"), ("GET", "/restaurants"),
        ("POST", "/products"), ("GET", "/products"), ("GET", "/products/{id}"),
        ("POST", "/cart/items"), ("GET", "/cart"),
        ("PATCH", "/cart/items/{id}"), ("DELETE", "/cart/items/{id}"),
        ("POST", "/orders"), ("GET", "/orders"), ("GET", "/orders/{id}"),
        ("PATCH", "/orders/{id}/status"), ("POST", "/payments"),
        ("GET", "/payments/{id}"), ("POST", "/deliveries/{id}/assign-driver"),
        ("PATCH", "/deliveries/{id}/status"),
    }
    assert len(required) == 20 and required <= actual
    for path in ("/products", "/products/search", "/restaurants", "/orders"):
        params = {p["name"] for p in app.openapi()["paths"][path]["get"]["parameters"]}
        assert {"page", "page_size", "sort", "limit", "sort_by", "order"} <= params


def test_product_restaurant_query_aliases_and_conflicts(client, catalogue):
    for path in ("/products", "/products/search"):
        filters = {"restaurant_id": str(catalogue["restaurant"].id), "search": "rice"}
        canonical = client.get(path, params={**filters, "page_size": 1, "sort": "-price"})
        aliases = client.get(path, params={**filters, "limit": 1, "sort_by": "price", "order": "desc"})
        assert aliases.status_code == 200 and aliases.json() == canonical.json()
        agreement = client.get(path, params={**filters, "page_size": 1, "limit": 1,
                                             "sort": "-price", "sort_by": "price", "order": "desc"})
        assert agreement.json() == canonical.json()
    canonical = client.get("/restaurants", params={"page_size": 1, "sort": "-name"})
    aliases = client.get("/restaurants", params={"limit": 1, "sort_by": "name", "order": "desc"})
    assert aliases.status_code == 200 and aliases.json() == canonical.json()
    for path in ("/products", "/products/search", "/restaurants"):
        for params in ({"limit": 0}, {"limit": 101}, {"limit": "bad"},
                       {"sort_by": "name; DROP TABLE users"}, {"order": "sideways"},
                       {"page_size": 1, "limit": 2}, {"sort": "name", "sort_by": "name", "order": "desc"}):
            response = client.get(path, params=params)
            assert response.status_code == 422, (path, params, response.text)
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_order_query_aliases_preserve_defaults_and_scope(client, orders):
    data, rows = orders
    header = auth(data["admin"])
    canonical = client.get("/orders", params={"page_size": 2, "sort": "placed_at"}, headers=header)
    aliases = client.get("/orders", params={"limit": 2, "sort_by": "placed_at", "order": "asc"}, headers=header)
    assert aliases.status_code == 200 and aliases.json() == canonical.json()
    assert client.get("/orders", params={"limit": 2}, headers=header).json() == client.get(
        "/orders", params={"page_size": 2}, headers=header).json()
    response = client.get("/orders", params={"limit": 1, "order": "asc",
                                              "restaurant_id": str(data["foreign_restaurant"].id)},
                          headers=auth(data["customer"]))
    assert response.status_code == 200 and response.json()["total"] == 0
    response = client.get("/orders", params={"limit": 1, "customer_id": str(rows[2].customer_id)},
                          headers=auth(data["customer"]))
    assert response.status_code == 403
    for params in ({"limit": 0}, {"limit": 101}, {"sort_by": "total; SELECT 1"},
                   {"order": "bad"}, {"page_size": 1, "limit": 2},
                   {"sort": "-placed_at", "sort_by": "placed_at", "order": "asc"}):
        response = client.get("/orders", params=params, headers=header)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
