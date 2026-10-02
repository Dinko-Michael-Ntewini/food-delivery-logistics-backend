from datetime import timedelta

import jwt
from sqlalchemy import select

from app.core.enums import UserRole
from app.core.security import create_access_token, hash_password, verify_password
from app.models.identity import User


PASSWORD = "correct-horse-battery-staple"


def register(client, email="customer@example.com", **extra):
    payload = {"email": email, "password": PASSWORD, "full_name": "Test Customer", **extra}
    return client.post("/auth/register", json=payload)


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def create_user(db_session, email, role, active=True):
    user = User(email=email, password_hash=hash_password(PASSWORD), full_name="Role User", role=role, is_active=active)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_customer_registration_hashes_password(client, db_session):
    response = register(client)
    assert response.status_code == 201
    assert response.json()["role"] == "CUSTOMER"
    user = db_session.scalar(select(User).where(User.email == "customer@example.com"))
    assert user.password_hash != PASSWORD
    assert verify_password(PASSWORD, user.password_hash)
    assert "password_hash" not in response.json()


def test_duplicate_invalid_email_and_privilege_escalation_rejected(client):
    assert register(client).status_code == 201
    assert register(client).status_code == 409
    assert register(client, email="not-an-email").status_code == 422
    assert register(client, email="admin@example.com", role="ADMIN").status_code == 403
    assert register(client, email="owner@example.com", role="RESTAURANT_OWNER").status_code == 403
    assert register(client, email="driver@example.com", role="DRIVER").status_code == 403


def test_login_and_me_return_safe_user(client):
    register(client)
    token_response = client.post("/auth/login", json={"email": "customer@example.com", "password": PASSWORD})
    assert token_response.status_code == 200
    token = token_response.json()["access_token"]
    me = client.get("/auth/me", headers=auth_header(token))
    assert me.status_code == 200
    assert me.json()["email"] == "customer@example.com"
    assert "password_hash" not in me.json()


def test_wrong_unknown_and_inactive_login_rejected(client, db_session):
    register(client)
    assert client.post("/auth/login", json={"email": "customer@example.com", "password": "wrong-password"}).status_code == 401
    assert client.post("/auth/login", json={"email": "unknown@example.com", "password": PASSWORD}).status_code == 401
    create_user(db_session, "inactive@example.com", UserRole.CUSTOMER, active=False)
    assert client.post("/auth/login", json={"email": "inactive@example.com", "password": PASSWORD}).status_code == 401


def test_missing_malformed_invalid_signature_and_expired_tokens_rejected(client, db_session):
    user = create_user(db_session, "token@example.com", UserRole.CUSTOMER)
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers=auth_header("not.a.jwt")).status_code == 401
    invalid_signature = jwt.encode({"sub": str(user.id)}, "other-secret-key-that-is-at-least-32-bytes", algorithm="HS256")
    assert client.get("/auth/me", headers=auth_header(invalid_signature)).status_code == 401
    expired = create_access_token(user.id, expires_delta=timedelta(seconds=-1))
    assert client.get("/auth/me", headers=auth_header(expired)).status_code == 401


def test_unknown_and_inactive_token_subjects_rejected(client, db_session):
    inactive = create_user(db_session, "inactive-token@example.com", UserRole.CUSTOMER, active=False)
    assert client.get("/auth/me", headers=auth_header(create_access_token(inactive.id))).status_code == 401
    assert client.get("/auth/me", headers=auth_header(create_access_token("00000000-0000-0000-0000-000000000001"))).status_code == 401


def test_rbac_admin_and_driver_guards(client, db_session):
    admin = create_user(db_session, "admin@example.com", UserRole.ADMIN)
    customer = create_user(db_session, "customer-role@example.com", UserRole.CUSTOMER)
    driver = create_user(db_session, "driver@example.com", UserRole.DRIVER)
    assert client.get("/auth/test/admin", headers=auth_header(create_access_token(admin.id))).status_code == 200
    assert client.get("/auth/test/admin", headers=auth_header(create_access_token(customer.id))).status_code == 403
    assert client.get("/auth/test/driver", headers=auth_header(create_access_token(driver.id))).status_code == 200
    assert client.get("/auth/test/driver", headers=auth_header(create_access_token(customer.id))).status_code == 403
    assert client.get("/auth/test/admin").status_code == 401
