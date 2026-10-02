from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import RoleChecker, get_current_active_user
from app.core.enums import UserRole
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.identity import User
from app.schemas.auth import AuthenticatedUserResponse, LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["authentication"])
InvalidCredentials = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password", headers={"WWW-Authenticate": "Bearer"})


@router.post("/register", response_model=AuthenticatedUserResponse, status_code=status.HTTP_201_CREATED)
def register_user(payload: RegisterRequest, db: Annotated[Session, Depends(get_db)]) -> User:
    email = str(payload.email).lower()
    if payload.role is not None and payload.role != UserRole.CUSTOMER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Public registration creates customer accounts only")
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")
    user = User(email=email, password_hash=hash_password(payload.password), full_name=payload.full_name.strip(), role=UserRole.CUSTOMER, is_active=True)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user is None or not verify_password(payload.password, user.password_hash) or not user.is_active:
        raise InvalidCredentials
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=AuthenticatedUserResponse)
def read_current_user(current_user: Annotated[User, Depends(get_current_active_user)]) -> User:
    return current_user


# Temporary internal guard probes; they contain no business functionality.
@router.get("/test/admin", dependencies=[Depends(RoleChecker(UserRole.ADMIN))], include_in_schema=False)
def admin_guard_probe() -> dict[str, str]:
    return {"status": "authorized"}


@router.get("/test/driver", dependencies=[Depends(RoleChecker(UserRole.DRIVER))], include_in_schema=False)
def driver_guard_probe() -> dict[str, str]:
    return {"status": "authorized"}
