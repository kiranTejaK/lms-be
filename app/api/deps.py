"""
FastAPI dependency injection functions.

Provides database sessions and authentication dependencies
used across all API endpoints via `Depends(...)`.
"""

from typing import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.user import User

login_token = OAuth2PasswordBearer(tokenUrl=f"{settings.APP_PREFIX}/v1/auth/login")

def get_db() -> Generator:
    """
    Yield a database session per request, ensuring cleanup on exit.

    Usage in endpoints:
        def my_endpoint(db: Session = Depends(get_db)):
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(login_token),
) -> User:
    """
    Decode the JWT and return the authenticated user.

    Raises 401 if the token is invalid or the user does not exist.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = security.verify_token(token)
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    result = db.execute(select(User).filter(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user account")
    return user

def get_current_active_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Require the current user to have an 'admin' role.

    Raises 403 if the user is not an admin.
    """
    role_names = [role.name for role in current_user.roles] if current_user.roles else []
    if "admin" not in role_names:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user
