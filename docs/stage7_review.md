# Stage 7 Review

> Historical stage snapshot. Earlier test counts, deferred capabilities and scope exclusions describe that stage only. For the final implementation, compatibility routes, constraints and verification results, see [Stage 10 review](stage10_review.md) and [final deliverables](final_deliverables.md).

| Check | Result | Evidence |
|---|---|---|
| Existing checkout Payment reused | PASS | Stage 6 creates one PENDING Payment; Stage 7 actions update that row, never add a replacement |
| Payment retrieval | PASS | `GET /payments/{payment_id}` and `GET /orders/{order_id}/payments` are order-ownership scoped |
| Payment state machine | PASS | PENDING → CAPTURED or FAILED; CAPTURED → REFUNDED only after successful refunds total the full amount |
| Confirmation | PASS | ADMIN-only `POST /payments/{payment_id}/confirm` checks pending status and Order total, sets internal reference and paid timestamp |
| Failure | PASS | ADMIN-only `POST /payments/{payment_id}/fail` changes PENDING to FAILED without deleting order/cart history |
| Refund creation | PASS | ADMIN-only `POST /payments/{payment_id}/refunds` creates an immediately SUCCEEDED internal Refund |
| Partial refund | PASS | Payment remains CAPTURED while successful refunds total less than its amount |
| Full refund | PASS | Exact full refund, direct or cumulative, sets Payment to REFUNDED |
| Over-refund protection | PASS | Validates positive two-decimal amount against remaining balance while holding the Payment row lock |
| Decimal handling | PASS | Numeric/Decimal amounts and server-calculated successful-refund sum; no float arithmetic or client balance |
| Ownership/RBAC | PASS | Customer views own; active restaurant owner/staff view scoped orders; ADMIN views and mutates; DRIVER denied |
| Concurrency protection | PASS | PostgreSQL-compatible `SELECT ... FOR UPDATE` serializes refund balance checks; SQLite tests do not emulate row locks |
| Rollback | PASS | Forced pre-commit failure leaves Refund absent and Payment status/balance unchanged |
| Stage 7 tests | PASS | `tests/test_payments.py` covers retrieval, lifecycle, partial/full/over-refunds, RBAC, rollback, OpenAPI, and end-to-end flow |
| Stage 1–6 regression | PASS | Previous 36 tests remain unchanged and pass in the full suite |
| Alembic | PASS | Existing Payment/Refund schema suffices; upgrade head and check show no pending changes |
| Swagger | PASS | Payments/Refunds routes have typed UUID/Decimal contracts, Bearer security, and no duplicate operation IDs |
| No Stage 8 delivery workflow | PASS | No Driver/Delivery business endpoint, assignment, or delivery state machine added |

`AUTHORIZED` remains an existing enum value but is not used by this manual simulation; confirmation moves directly from PENDING to CAPTURED. `RefundStatus.SUCCEEDED` is applied immediately because no external provider is called. `PENDING` and `FAILED` refund statuses are reserved for a future provider-backed process. Only successful refunds reduce the remaining balance. `remaining_refundable` is the arithmetic payment balance; PENDING and FAILED payments still cannot be refunded because the status precondition is enforced. Payment and Order snapshots/history are not changed by refunds.
