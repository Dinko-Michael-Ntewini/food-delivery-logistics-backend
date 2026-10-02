# Food Delivery & Logistics Platform Backend

## Overview / features

FastAPI backend for restaurant catalogues, customer ordering, manual payments/refunds and driver dispatch. Exactly 20 domain entities and 70 business OpenAPI operations (72 including system health routes). Checkout and delivery/order synchronization are transactional; access is role- and ownership-scoped.

## Tech stack / architecture

Python 3.11+, FastAPI, Pydantic/settings, SQLAlchemy 2, Alembic, PyJWT, Argon2 via pwdlib, Uvicorn, psycopg, pytest and HTTPX. See requirements.txt; final verification used Python 3.14.

```text
app/api/       HTTP routes and authentication dependencies
app/core/      configuration, security and normalized errors
app/db/        metadata and sessions
app/models/    20 SQLAlchemy entities
app/schemas/   validated request/response contracts
app/services/  scoped queries and transactional business operations
alembic/       six chained revisions
tests/         isolated tests and migrated-database integration
scripts/       trusted administrator bootstrap
postman/       collection and safe local environment
docs/          ER diagram, data model, RBAC and stage reviews
```

## Core 20 entities / relationships

User, Address, CustomerProfile, Restaurant, RestaurantBranch, RestaurantStaff, Menu, Category, Product, ProductVariant, Cart, CartItem, Order, OrderItem, OrderStatusHistory, Payment, Refund, Driver, Delivery, DeliveryStatusHistory.

One-to-one: User/CustomerProfile, User/Driver, Order/Delivery.
One-to-many: addresses; restaurant branches/menus; menu categories; category products; product variants; cart items; order items/history/payments; payment refunds; driver deliveries; delivery history.
Many-to-many: User/Restaurant through RestaurantStaff.

See [ER diagram](docs/er_diagram.md), [data model](docs/data_model.md) and [RBAC](docs/rbac_matrix.md).

## Installation

Run from the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

POSIX: activate with `source .venv/bin/activate`; copy with `cp .env.example .env`. Edit .env before startup. Never commit it.

## Environment variables

| Variable | Purpose |
|---|---|
| APP_NAME | Service name |
| APP_ENV | development locally; production enables signing-key validation |
| DEBUG | Configuration flag; HTTP traceback responses remain disabled |
| DATABASE_URL | SQLite or PostgreSQL SQLAlchemy URL |
| SECRET_KEY | JWT signing key; unique and at least 32 characters in production |
| ACCESS_TOKEN_EXPIRE_MINUTES | Positive lifetime, default 30 |
| JWT_ALGORITHM | HS256 only |
| ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_FULL_NAME | Bootstrap shell variables, not automatically loaded from .env by the script |

Example credentials are placeholders. Generate a private random signing key. Production rejects the default signing key and short keys.

## Database / Alembic / running migrations

```powershell
python -m alembic upgrade head
python -m alembic check
python -m alembic current
```

Single final head: `c5b21d4e8f32`. Six revisions implement UUID/FK constraints and partial indexes for memberships, default addresses and active carts/cart lines. One active delivery per driver is enforced by service eligibility checks and driver-row locks where supported, not a partial unique index. SQLite connections enable foreign keys. Application setup uses migrations, not create_all.

## Creating the initial admin

After migrations, supply credentials privately:

```powershell
$env:ADMIN_EMAIL = Read-Host 'Admin email'
$bootstrapPassword = Read-Host 'Admin password' -AsSecureString
$env:ADMIN_PASSWORD = [System.Net.NetworkCredential]::new('', $bootstrapPassword).Password
$env:ADMIN_FULL_NAME = 'Platform Administrator'
python scripts/create_admin.py
Remove-Item Env:ADMIN_PASSWORD
Remove-Variable bootstrapPassword
```

POSIX users set the same ADMIN_* shell variables privately. Owner, STAFF and DRIVER User accounts require trusted provisioning using the existing password-hashing utility; there is no public privileged-registration/user-management API. ADMIN creates Driver profiles for existing active DRIVER users.

## Running locally / Swagger

```powershell
python -m uvicorn app.main:app --reload
```

Default port: 8000. Swagger: http://127.0.0.1:8000/docs; schema: /openapi.json. GET / and GET /health are public. Final live verification uses port 8021.

## Authentication / RBAC roles

POST /auth/register creates only CUSTOMER users. POST /auth/login returns a Bearer JWT; GET /auth/me returns safe user data. Passwords use Argon2; signature, subject and mandatory expiration are validated. Inactive accounts are rejected. Hashes never appear in response schemas.

| Role | Permissions |
|---|---|
| ADMIN | Global catalogue, financial administration and driver management |
| RESTAURANT_OWNER | Active owned-restaurant membership and restaurant resources |
| STAFF | Active membership; global MANAGER catalogue rights and scoped order/dispatch rights |
| CUSTOMER | Own profile/addresses/cart/orders and financial/delivery visibility |
| DRIVER | Own driver profile and assigned deliveries |

Out-of-scope IDs generally return 404; forbidden capabilities return 403. Filtering never widens ownership scope.

## Restaurant / catalogue

Restaurants contain branches/menus; menus contain categories/products/variants. The final active owner cannot be removed. Membership uniqueness handles null/global branch scope. Catalogue managers need active global MANAGER membership. A variant may have price_override or price_delta, never both. Availability and valid nonnegative effective prices are enforced; snapshots preserve historical orders.

## Customer / address / cart

CUSTOMER endpoints: /customers/me/profile and /customers/me/addresses. Default changes clear the prior default; a partial unique index separately enforces at most one per user. Deleting an order-referenced address returns 409.

GET /cart fetches/creates the customer's active cart. The first POST /cart/items requires explicit branch_id: active and from the product restaurant. Later items may omit it but must match that branch/restaurant; mismatch returns 409. No sole-branch inference. Product/variant/ancestor availability is checked. Duplicate selections increment quantity; deleting the last item clears branch_id.

Decimal prices: base, variant override, or base plus delta. Line total = unit price times quantity; subtotal = sum of line totals, with two-place monetary handling. Client-supplied prices are forbidden.

## Order / checkout / order state machine

POST /orders/checkout and original-brief alias POST /orders accept address_id and payment_method (CASH_ON_DELIVERY or MOBILE_MONEY). One transaction validates/locks the cart, recalculates prices, creates Order/OrderItems, immutable name/price/address snapshots, initial history and PENDING Payment, then clears cart/branch. Failure rolls everything back.

```text
PENDING -> CONFIRMED -> PREPARING -> READY_FOR_PICKUP -> OUT_FOR_DELIVERY -> DELIVERED
```

Only adjacent transitions are accepted. Repeat/skip/backward/terminal changes return 409. Restaurant actors prepare orders. Linked Delivery physical transitions use the Delivery API; ADMIN may directly progress legal states without a Delivery. Histories are append-only through application APIs.

## Payments / refunds

Checkout creates one PENDING Payment in GHS. POST /payments with order_id idempotently returns that existing payment to its customer or ADMIN; it does not create a second record or accept a client amount. Financial GET routes are scoped.

ADMIN simulates PENDING -> CAPTURED or PENDING -> FAILED. Partial refunds leave CAPTURED; accumulated full refunds produce REFUNDED. Decimal refunds cannot exceed captured balance; locks/transactions protect changes where supported. PENDING/FAILED cannot be refunded. AUTHORIZED is a reserved enum, not an implemented transition. No external processor or live money transfer.

## Driver / delivery / delivery state machine

ADMIN manages Driver profiles; DRIVER safely reads/updates its own profile. ADMIN/scoped restaurant actors create delivery for READY_FOR_PICKUP. POST /deliveries/{delivery_id}/assign-driver and PATCH /deliveries/{delivery_id}/assign assign an active available driver. At most one active delivery per driver. Pre-pickup reassignment appends an old/new-driver audit note.

```text
UNASSIGNED -> ASSIGNED -> PICKED_UP -> IN_TRANSIT -> DELIVERED
```

Only assigned DRIVER or ADMIN makes physical transitions. Pickup synchronizes Order to OUT_FOR_DELIVERY; transit retains it; completion sets DELIVERED. Both records/histories commit atomically. Terminal changes are rejected; read access remains scoped.

## Search / filtering / pagination / sorting

Products: name, category, restaurant, min/max base price, availability. Restaurants: search, city/location, active. Orders: status, restaurant, branch, dates, order number; customer filter is ADMIN-only. Other Stage 9 filters preserve scope.

Primary paged lists return items, total, page, page_size; pages start at 1, size is 1-100. Sort fields are allowlisted; '-' means descending, stable ID tie-breakers apply. Nested lists may remain arrays. Dates normalize to UTC. Queries use parameterized SQLAlchemy expressions, not interpolated raw SQL.

Product, restaurant and order lists also support the brief's backward-compatible aliases: limit for page_size, sort_by for an allowlisted field, and order=asc|desc. Existing page_size/sort remain supported. Conflicting canonical/alias values return 422; matching values are allowed. Omitting order retains the canonical default direction. Category filtering uses category_id, not a category-name string.

## Centralized error handling

401/403/404/409/422 use ErrorResponse. Validation details omit raw sensitive inputs. IntegrityError rolls back and becomes a safe conflict; unexpected errors return generic 500 without SQL, secrets, traces or local paths.

## Running tests

```powershell
python -m compileall -q app tests
python -m alembic upgrade head
python -m alembic check
python -m pytest --collect-only -q
python -m pytest tests -q -p no:cacheprovider
python -m pytest tests/test_final_system.py -q -p no:cacheprovider
```

83 tests: the original 80 Stage 10 tests plus three pre-publication route/query-compatibility tests. The integration fixture migrates a disposable empty in-memory DB from zero, checks drift and executes catalogue/customer checkout through delivered status, snapshots and unauthorized access checks. The developer DB is preserved. Existing financial tests separately cover refunds/rollback.

## Postman

Import [collection](postman/Food_Delivery_Logistics_API.postman_collection.json) and [local environment](postman/Food_Delivery_Local.postman_environment.json). Select Food Delivery Local and privately supply credentials. Tokens/IDs/passwords start empty. Scripts save tokens and created IDs using actual response fields.

81 requests in 17 folders cover all 72 OpenAPI operations (70 business). Examples match actual schemas; public requests are noauth, protected requests use role-token variables.

Use the selected flow: role login/setup -> catalogue -> customer/address/cart -> checkout -> POST /payments to save payment_id -> capture -> legal preparation -> delivery/assignment -> pickup/transit/completion. Do not run every mutation blindly: aliases, refunds/failures and deletes are alternative scenarios.

## Security notes

Keep .env, real credentials, databases/logs and tokens out of source control. Production needs HTTPS and least-privilege DB accounts. Privileged provisioning is trusted, never public registration. Hidden role-guard probes are excluded from Swagger/counts. Examples contain placeholders only.

## PostgreSQL production setup

Install requirements including psycopg; provision a least-privilege database user and configure:

```dotenv
APP_ENV=production
DEBUG=false
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/food_delivery
SECRET_KEY=<private-random-key-of-at-least-32-characters>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

Migrate/check before startup. UUID/Numeric, non-native enums, Boolean/partial indexes, Alembic and row locks were statically inspected; all 20 tables and indexes compile for PostgreSQL. NOT LIVE-TESTED ON POSTGRESQL. SQLite tests do not prove PostgreSQL concurrency; validate a real deployment before production.

## Known development limitations

Internal payment simulation; zero delivery fee by default; trusted privileged-User provisioning beyond admin bootstrap. SQLite has limited write concurrency and no row-level FOR UPDATE. No frontend/GPS/gateway/notification/infrastructure expansion. Upstream Starlette/AnyIO deprecation warnings are non-failing.

## Project status

All ten stages complete. See [final deliverables](docs/final_deliverables.md), [Stage 10 review](docs/stage10_review.md) and [pre-GitHub audit](docs/pre_github_review.md) for evidence. Earlier reviews are historical snapshots, not the final inventory. A local Git repository has now been initialized on main using the existing configured identity. GitHub publication is awaiting the intended repository URL; no remote or push has been created.
