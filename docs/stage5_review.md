# Stage 5 Review

> Historical stage snapshot. Earlier test counts, deferred capabilities and scope exclusions describe that stage only. For the final implementation, compatibility routes, constraints and verification results, see [Stage 10 review](stage10_review.md) and [final deliverables](final_deliverables.md).

This is the historical Stage 5 completion review. Stage 6 order checkout and status workflows are documented separately in `stage6_review.md`.

Pre-Stage-6 audit update: migration `b4a10f3c7a21` adds a partial unique index for one active cart per customer; `c5b21d4e8f32` makes the future order item's variant-name snapshot optional, consistent with Stage 5's variant-free cart items. No checkout workflow was added. The audit also verifies default-address switching through PATCH, JWT expiration enforcement, owner/staff scope, variant partial updates, and strict search validation in `tests/test_integrity_audit.py`. The table below records the original Stage 5 completion checks; current suite totals are in the audit report.

| Requirement | Result | Verification |
|---|---|---|
| Customer profile read, update, and ownership | PASS | `tests/test_customers.py`; CUSTOMER-only `/customers/me/profile` routes |
| Address create, list, get, update, delete, and ownership | PASS | `tests/test_customers.py`; UUID-scoped current-user routes |
| Default address logic and partial unique index | PASS | Second default clears the first in customer test; migration `e8e1cb5f1505` and Alembic check |
| Cart retrieval and customer ownership | PASS | Empty and separate customer carts plus role checks in `tests/test_cart.py` |
| Explicit first-item branch and later branch reuse | PASS | Missing, inactive, foreign, matching, and omitted branches exercised in cart tests |
| Branch and restaurant conflicts | PASS | Different branch and restaurant return 409 in end-to-end cart test |
| Empty-cart branch reset | PASS | Deleting all items clears branch; next item again requires explicit branch |
| Product and variant validation | PASS | Missing product/variant, mismatched variant, and unavailable product/variant tests |
| Availability of existing items | PASS | Previously added items remain visible with current product/variant availability flags |
| Duplicate item increment | PASS | Identical plain and variant selections increment quantity without another row |
| Quantity update and item deletion | PASS | Positive quantity PATCH, zero/negative rejection, owner-only DELETE |
| Decimal unit pricing, line totals, and subtotal | PASS | Base, price delta, override, duplicate, and quantity-change values asserted with `Decimal` |
| Stage 5 migrations and constraints | PASS | `e8e1cb5f1505` and `57256a84ce7e` applied; nullable branch/variant and product FK inspected |
| Alembic upgrade and check | PASS | `python -m alembic upgrade head`; `python -m alembic check` found no pending changes |
| Stage 5 tests | PASS | `python -m pytest tests/test_cart.py -q -p no:cacheprovider`: 5 passed |
| Stage 3, Stage 4, and Stage 5A regression | PASS | Original Stage 5 completion: 15 passed; pre-Stage-6 audit: 21 passed with six added regression/integration/OpenAPI tests |
| Swagger/OpenAPI and Bearer security | PASS | `/docs` HTTP 200; all cart operations, security declarations, tags, and schemas inspected |
| Representative end-to-end cart flow | PASS | `test_full_cart_flow_pricing_duplicates_ownership_and_reset` exercises authenticated creation, pricing, conflicts, ownership, removal, reset, and reuse |
| Stage 6 functionality at Stage 5 completion | PASS | No checkout or order/payment/delivery business workflow was added during Stage 5 |

The Stage 2 cart schema could not represent an empty unscoped cart or a product without a variant. Migration `57256a84ce7e` made `carts.branch_id` and `cart_items.product_variant_id` nullable and added `cart_items.product_id`; existing variant-backed rows are backfilled from `product_variants`. The migration retains foreign keys and uses SQLite batch alteration. Cart prices reflect the current catalogue and are not order snapshots.

Verification was against the isolated SQLite test database and local SQLite migration database. PostgreSQL compatibility is expressed in SQLAlchemy/Alembic metadata but was not exercised against a live PostgreSQL server.
