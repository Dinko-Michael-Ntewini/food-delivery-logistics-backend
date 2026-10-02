from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.enums import UserRole
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.identity import User

bearer_scheme = HTTPBearer(auto_error=False)
CredentialsError = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})


def get_current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)], db: Annotated[Session, Depends(get_db)]) -> User:
    if credentials is None:
        raise CredentialsError
    try:
        user_id = decode_access_token(credentials.credentials)
    except ValueError:
        raise CredentialsError
    user = db.get(User, user_id)
    if user is None:
        raise CredentialsError
    return user


def get_current_active_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user", headers={"WWW-Authenticate": "Bearer"})
    return current_user


class RoleChecker:
    def __init__(self, *allowed_roles: UserRole) -> None:
        self.allowed_roles = frozenset(allowed_roles)

    def __call__(self, current_user: Annotated[User, Depends(get_current_active_user)]) -> User:
        if current_user.role not in self.allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user


def require_roles(*roles: UserRole) -> Callable[..., User]:
    return RoleChecker(*roles)
