# Stage 6 Review

> Historical stage snapshot. Earlier test counts, deferred capabilities and scope exclusions describe that stage only. For the final implementation, compatibility routes, constraints and verification results, see [Stage 10 review](stage10_review.md) and [final deliverables](final_deliverables.md).

This is the historical Stage 6 completion review. Stage 7 manual payment and refund actions are documented in `stage7_review.md`.

| Check | Result | Evidence |
|---|---|---|
| Checkout endpoint | PASS | `POST /orders/checkout` accepts only customer-owned address ID and a supported payment method |
| Checkout validation | PASS | Role, nonempty scoped cart, active branch/restaurant/catalogue, variant relationship, quantity, and address ownership checked |
| Atomic transaction | PASS | Order, items, initial history, pending Payment, and cart clear are flushed and committed together |
| Order creation | PASS | Unique order number, customer/branch, PENDING status, Decimal subtotal/total |
| OrderItem snapshots | PASS | Checkout-time names, optional variant ID/name, unit price, quantity, line total, and notes persisted |
| Address snapshot | PASS | Delivery contact/location copied to JSON; later Address edits do not change it |
| Initial PENDING state | PASS | New order begins PENDING |
| Initial status history | PASS | One PENDING entry with checkout actor and timestamp |
| Initial Payment record | PASS | PENDING amount equals order total; currency GHS and selected method stored, without capture |
| Cart clearing | PASS | All checked-out CartItems removed only within successful transaction |
| Cart branch reset | PASS | Cart branch becomes NULL after successful checkout |
| Rollback behavior | PASS | Forced pre-commit failure leaves no order/items/history/payment and preserves cart/branch |
| Customer order listing | PASS | `GET /orders` returns only own orders with bounded pagination and status filter |
| Order detail | PASS | `GET /orders/{order_id}` returns safe snapshots and history |
| Restaurant ownership | PASS | Active owner/global or appropriately branch-scoped staff membership required; unrelated actors denied |
| Customer ownership | PASS | Other customers cannot list or read the order |
| Exact state machine | PASS | PENDING → CONFIRMED → PREPARING → READY_FOR_PICKUP → OUT_FOR_DELIVERY → DELIVERED |
| Invalid jump rejection | PASS | Skipped and same-state transitions return 409 |
| Backward rejection | PASS | Backward and post-DELIVERED transitions return 409 |
| Append-only history | PASS | Each successful transition inserts a new history row; `GET /orders/{order_id}/status-history` is chronological |
| Decimal totals | PASS | Current catalogue Decimal prices are recalculated at checkout; delivery fee is 0.00 until a fee policy exists |
| Stage 6 tests | PASS | `tests/test_orders.py` covers checkout, rollback, snapshots, RBAC, exact transitions, OpenAPI, and an API-driven flow |
| Stage 1–5 regression | PASS | Existing 21 tests remain unchanged and pass in the full suite |
| Alembic | PASS | Existing schema suffices; upgrade head and check report no pending changes |
| Swagger | PASS | Orders-tagged paths, typed schemas, Bearer protection, no duplicate operation IDs |
| No Stage 7/8 workflow leakage at Stage 6 completion | PASS | No capture/refund or driver/delivery workflow was added during Stage 6 |

Stage 6 stores `Payment.provider` as the customer's selected method (`CASH_ON_DELIVERY` or `MOBILE_MONEY`) and uses `GHS` because the current schema requires a currency. The Payment stays PENDING; Stage 7 owns processing and refund policy. Delivery fee is explicitly zero because no fee schedule exists yet. Only ADMIN may perform the delivery-oriented `OUT_FOR_DELIVERY` and `DELIVERED` transitions in Stage 6; Stage 8 must bind them to assigned-driver/delivery authorization.
