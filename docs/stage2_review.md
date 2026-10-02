# Stage 2 Review

> Historical stage snapshot. Earlier test counts, deferred capabilities and scope exclusions describe that stage only. For the final implementation, compatibility routes, constraints and verification results, see [Stage 10 review](stage10_review.md) and [final deliverables](final_deliverables.md).

| Verification | Result | Evidence |
|---|---|---|
| FastAPI project structure created | PASS | `app/` package with core, db, models, schemas, api, services, and main application |
| Environment configuration created | PASS | `app/core/config.py` and `.env.example` provide APP_NAME, APP_ENV, DEBUG, DATABASE_URL |
| SQLAlchemy configured | PASS | SQLAlchemy 2.x declarative Base, naming convention, engine, session factory, and dependency |
| Exactly 20 required models implemented | PASS | metadata import reports 20 business tables |
| UUID keys used | PASS | all entity primary keys use `Uuid(as_uuid=True)` |
| Decimal/Numeric money used | PASS | all monetary fields use `Numeric(12,2)` with non-negative checks |
| Required relationships implemented | PASS | bidirectional `back_populates` mappings configure without warnings |
| One-to-one verified | PASS | unique User–CustomerProfile, User–Driver, and Order–Delivery FKs |
| One-to-many verified | PASS | catalogue, cart, order, payment, driver, and delivery collections mapped |
| Many-to-many via RestaurantStaff verified | PASS | User and Restaurant each relate to `RestaurantStaff` membership rows |
| Enums implemented | PASS | user, staff, cart, order, payment, refund, and delivery enums defined |
| Historical order snapshots supported | PASS | Order address JSON and OrderItem name/variant/price snapshots are persisted |
| Alembic initialized | PASS | application metadata is loaded by `alembic/env.py` |
| Initial migration generated | PASS | `91b9633d792d_initial_20_entity_schema.py` |
| Initial migration tested | PASS | applied to a fresh SQLite local database; 20 business tables plus `alembic_version` present |
| FastAPI starts and system routes work | PASS | TestClient received HTTP 200 from `/`, `/health`, and `/docs` |
| Authentication/business endpoints absent | PASS | only system identification and health endpoints exist |

## Scope boundary

No registration, login, JWT, password hashing behavior, authorization enforcement, restaurant/catalogue/cart/order/payment/refund/delivery operations, state machine logic, or feature endpoints were implemented.

## Notes for later stages

- Payment/refund totals and order/delivery state transitions require service-layer transactional validation.
- The optional `RestaurantStaff.branch_id` needs a database-specific null-safe uniqueness strategy in the PostgreSQL migration stage if global and branch-scoped memberships are both enabled.
- A partial unique index for one default address per user remains a PostgreSQL migration enhancement.
