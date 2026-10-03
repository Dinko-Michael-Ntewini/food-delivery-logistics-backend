# Live PostgreSQL verification

Date: 2026-10-03. Result: PASS.

Server: PostgreSQL 17.10, official `postgres:17-alpine` Docker image, Linux/amd64. A temporary container exposed only to localhost used a disposable `test_zaptek` database and generated credentials. No developer SQLite database or production database was accessed. The temporary container and its database were removed after verification; the cached image remains.

## Observed results

| Check | Result |
| --- | --- |
| `python -m compileall -q app tests` | PASS |
| `python -m alembic upgrade head` | All six revisions applied on PostgreSQL |
| `python -m alembic check` | No new upgrade operations detected |
| `python -m alembic downgrade base`, then upgrade/check | PASS on the empty disposable database |
| `python -m pytest tests -q -p no:cacheprovider`, with `TEST_POSTGRES_URL` set | 83 passed, 0 failed, 0 skipped; 330.02 seconds |
| Same suite with SQLite default | 83 passed, 0 failed, 0 skipped; 116.56 seconds |
| Two independent PostgreSQL connections contending for `SELECT ... FOR UPDATE` | Second connection timed out while locked, then succeeded after release |
| Uvicorn connected to PostgreSQL, port 8014 | `/`, `/health`, `/docs`, `/openapi.json`: HTTP 200 |
| Live HTTP registration/login/profile/addresses/cart | PASS; registered UUID/user verified directly in PostgreSQL |
| Temporary per-test schema cleanup | PASS; no test schemas remained |

The existing suite covers customer/address/cart rules, pricing, ownership and authorization, checkout, payment/refund behavior, driver/delivery transitions, rollback checks, and Postman/OpenAPI artifacts. Its full customer-to-delivered API workflow ran against a freshly Alembic-migrated PostgreSQL schema, including snapshot preservation and histories. Other database-backed tests use SQLAlchemy metadata in individually isolated PostgreSQL schemas.

Two existing Starlette/AnyIO dependency deprecation warnings remain; no application failure occurred.

## Repeating the suite

Provision a disposable database named `test_*`, install the existing requirements, and supply `TEST_POSTGRES_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/test_DATABASE` through the process environment. The account needs permission to create/drop its own schemas. Run the pytest command above. SQLite remains the default if the variable is absent. For CLI migrations and Uvicorn, also set `DATABASE_URL` to the disposable URL and supply a valid `SECRET_KEY`.

Only test infrastructure and documentation changed; no application/model/migration change was necessary. SQLite-only PRAGMA checks now select equivalent PostgreSQL foreign-key catalog checks when that backend is active. Assertions and API behavior were not weakened.

This supersedes earlier static-only PostgreSQL compatibility statements. It does not certify production deployment, concurrent business-request stress tests, TLS, backups, failover, or performance under load. The lock probe proves database locking itself, not every business race condition.
