"""Create an initial ADMIN account from environment variables.

Set ADMIN_EMAIL, ADMIN_PASSWORD, and optionally ADMIN_FULL_NAME, then run:
python scripts/create_admin.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from app.core.enums import UserRole
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.identity import User


def main() -> int:
    raw_email = os.getenv("ADMIN_EMAIL", "")
    password = os.getenv("ADMIN_PASSWORD", "")
    full_name = os.getenv("ADMIN_FULL_NAME", "Platform Administrator").strip()
    try:
        email = str(TypeAdapter(EmailStr).validate_python(raw_email)).lower()
    except ValidationError:
        print("ADMIN_EMAIL must be a valid email address.", file=sys.stderr)
        return 2
    if not 8 <= len(password) <= 128:
        print("ADMIN_PASSWORD must contain 8 to 128 characters.", file=sys.stderr)
        return 2
    if not full_name or len(full_name) > 150:
        print("ADMIN_FULL_NAME must contain 1 to 150 characters.", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == email)) is not None:
            print("An account with this email already exists.", file=sys.stderr)
            return 1
        db.add(User(email=email, password_hash=hash_password(password), full_name=full_name, role=UserRole.ADMIN, is_active=True))
        db.commit()
    print(f"Created ADMIN account for {email}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
