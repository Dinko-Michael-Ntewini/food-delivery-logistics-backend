# Stage 8 Review

> Historical stage snapshot. Earlier test counts, deferred capabilities and scope exclusions describe that stage only. For the final implementation, compatibility routes, constraints and verification results, see [Stage 10 review](stage10_review.md) and [final deliverables](final_deliverables.md).

| Check | Result | Evidence |
|---|---|---|
| Driver profile | PASS | Existing one-to-one Driver/User model; ADMIN creates profiles only for active DRIVER users |
| Driver RBAC | PASS | ADMIN lists/manages; DRIVER reads/updates own safe vehicle/availability fields; user_id cannot change |
| Delivery creation | PASS | ADMIN or authorized restaurant actor; Order must be READY_FOR_PICKUP |
| One Delivery per Order | PASS | Existing unique order_id plus service validation and order-row lock |
| Driver assignment | PASS | Valid, active DRIVER user, available profile, no other active delivery |
| Reassignment | PASS | Allowed only before pickup; appended ASSIGNED assignment event records old/new driver IDs and actor |
| Exact state machine | PASS | UNASSIGNED -> ASSIGNED -> PICKED_UP -> IN_TRANSIT -> DELIVERED; assignment uses its dedicated endpoint |
| Assigned-driver authorization | PASS | Operational transitions are restricted to ADMIN or the current assigned DRIVER, rechecked after locking |
| DeliveryStatusHistory | PASS | Initial and transition rows appended with actor, timestamp and optional note; chronological retrieval |
| Order synchronization | PASS | Pickup moves READY_FOR_PICKUP to OUT_FOR_DELIVERY; completion moves OUT_FOR_DELIVERY to DELIVERED |
| OrderStatusHistory synchronization | PASS | Shared Stage 6 next-state function appends Order history within the delivery transaction |
| Atomic transitions | PASS | Delivery, Order and both history writes share one commit; errors roll back |
| Rollback behavior | PASS | Forced pre-commit failures during PICKED_UP and DELIVERED restore both records and both histories |
| Completed-delivery immutability | PASS | Terminal state; no reassignment or deletion endpoint; linked Order cannot advance independently |
| Customer visibility | PASS | Only deliveries belonging to own Orders |
| Restaurant visibility | PASS | Active global OWNER or active global/branch STAFF/MANAGER membership, using existing Order visibility rules |
| Driver visibility | PASS | Only deliveries currently assigned to own Driver profile |
| Active-delivery safety | PASS | One active ASSIGNED/PICKED_UP/IN_TRANSIT delivery per driver; unavailable change rejected while active |
| Stage 8 tests | PASS | 12 passed, 0 failed, 0 skipped; includes API-driven end-to-end flow and financial/snapshot integrity |
| Stages 1-7 regression | PASS | 57 total tests pass, including the unchanged 45-test baseline |
| Alembic | PASS | No model changes or new migration; upgrade head and check pass at c5b21d4e8f32 |
| Swagger | PASS | Contract tests cover tags, Bearer security, UUIDs, enums, safe fields and unique operation IDs; live /docs and /openapi.json return 200 |
| No Stage 9 scope leakage | PASS | No global error/search/pagination framework or broad optimization added |

## Policies and limits

- Driver account provisioning remains outside public customer registration. ADMIN uses `POST /drivers` to attach a profile to an existing active DRIVER user. The directory is ADMIN-only; restaurant dispatchers assign a known Driver ID and cannot edit profiles.
- `is_available` represents driver willingness. Active-assignment checks independently prevent multiple simultaneous deliveries. A driver becomes eligible for another assignment after completion or reassignment, if still available.
- Reassignment appends an `ASSIGNED -> ASSIGNED` audit event with old/new driver IDs. It is not a same-state transition through the status endpoint: all same-state status requests and repeat assignments to the same driver are rejected.
- There is no User role/deactivation business endpoint. Driver profile updates cannot modify User activity/role or linked user_id, and cannot mark a driver unavailable while a delivery is active. No Driver deletion route is exposed.
- Creation locks Order; dispatch and transitions lock Order then Delivery; assignment also locks the target Driver before checking conflicts. These row locks target databases supporting `FOR UPDATE`. SQLite ignores row locks, so the local suite verifies sequential conflict checks and rollback, not PostgreSQL concurrent dispatch behavior.
- Direct Stage 6 ADMIN transitions remain available for orders without a Delivery, preserving existing behavior. Once a Delivery exists, delivery-related Order changes must use the synchronized Delivery workflow. Driver access is through Delivery APIs; direct Order APIs keep existing permissions.
- Delivery actions do not modify Payment, Refund, OrderItem/address snapshots, or Cart state.

## Verification evidence

| Command/check | Result | Evidence |
|---|---|---|
| `python -m compileall -q app tests` | PASS | Exit 0 |
| `python -m alembic upgrade head` | PASS | Exit 0 |
| `python -m alembic check` | PASS | No new upgrade operations detected |
| `python -m pytest --collect-only -q` | PASS | 57 tests collected |
| `python -m pytest tests/test_deliveries.py -q -p no:cacheprovider` | PASS | 12 passed, 0 failed, 0 skipped |
| `python -m pytest tests -q -p no:cacheprovider` | PASS | 57 passed, 0 failed, 0 skipped |
| API-driven Stage 8 end-to-end | PASS | Existing cart/checkout APIs, legal preparation, dispatch, driver login, pickup/transit/completion, histories, denied access and unchanged financial/snapshot/cart records |
| `python -m uvicorn app.main:app --host 127.0.0.1 --port 8019` | PASS | Startup complete; GET /, /health, /docs, /openapi.json all 200; verification server stopped afterward |

The test runs emitted two dependency deprecation warnings from Starlette/AnyIO, with no failures or skips. PostgreSQL concurrent dispatch has not been exercised by this SQLite suite.
