# Stage 3 Review

> Historical stage snapshot. Earlier test counts, deferred capabilities and scope exclusions describe that stage only. For the final implementation, compatibility routes, constraints and verification results, see [Stage 10 review](stage10_review.md) and [final deliverables](final_deliverables.md).

| Verification | Result | Evidence |
|---|---|---|
| Secure password hashing | PASS | `pwdlib` with Argon2 recommended hashing configuration |
| Registration works | PASS | public `POST /auth/register` test passes |
| Public privilege escalation prevented | PASS | public registration permits CUSTOMER only |
| Duplicate email prevented | PASS | normalized-email lookup and database unique constraint return 409 |
| Login works | PASS | valid credentials receive a Bearer access token |
| JWT created | PASS | PyJWT produces minimal signed `sub` and `exp` claims |
| JWT expiration enforced | PASS | expired-token test returns 401 |
| Invalid JWT rejected | PASS | malformed and invalid-signature tests return 401 |
| GET /auth/me protected | PASS | requires valid Bearer token and active user |
| Inactive users rejected | PASS | login and authenticated access tests return 401 |
| RBAC reusable | PASS | `RoleChecker` and `require_roles` dependencies |
| All five roles supported | PASS | ADMIN, RESTAURANT_OWNER, STAFF, CUSTOMER, DRIVER use the existing UserRole enum |
| 401 vs 403 correct | PASS | missing/invalid credentials return 401; wrong authenticated role returns 403 |
| Admin bootstrap supported | PASS | `scripts/create_admin.py` reads validated environment values |
| Tests implemented | PASS | isolated SQLite pytest fixtures and seven auth/RBAC tests |
| Tests pass | PASS | `python -m pytest -q -p no:cacheprovider`: 7 passed |
| Swagger authentication | PASS | HTTP Bearer security scheme and auth endpoints appear in OpenAPI; `/auth/login` accepts JSON credentials |
| No Stage 4+ business functionality | PASS | only authentication and temporary internal RBAC guard probes were added |

## Security decisions

- Public registration always creates a CUSTOMER account, even if the role is omitted; attempts to request privileged roles are rejected.
- Password hashes are Argon2 salted hashes; plaintext passwords are not persisted or returned.
- JWT tokens use the environment-configured algorithm (HS256 by default), include only user ID subject and expiration, and are validated before loading a user.
- Temporary `/auth/test/admin` and `/auth/test/driver` routes are intentionally excluded from OpenAPI and exist solely to exercise generic guards until business routes are added.

## Migration status

No Stage 3 migration was required: the Stage 2 User model already included identity, password-hash, role, active-state, and timestamp fields. `python -m alembic check` reported no pending schema changes.
