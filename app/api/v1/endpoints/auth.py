"""
Authentication endpoints: login, register, token refresh, current user,
change password, and logout.
"""

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.schemas.user import ChangePassword, Token, TokenRefresh, UserCreate, UserResponse
from app.services.auth_service import AuthService
from app.services.user_service import UserService

router = APIRouter()

#completed
@router.post("/register", response_model=UserResponse)
def register(
    user_in: UserCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(deps.get_db)
):
    """Register a new user account."""
    svc = UserService(db)
    return svc.create_user(user_in, background_tasks)
#completed
@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(deps.get_current_user)):
    """Return the currently authenticated user's details."""
    return current_user

#completed
@router.post("/login", response_model=Token)
def login(db: Session = Depends(deps.get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate with email + password, returns JWT token pair."""
    svc = AuthService(db)
    return svc.login(form_data)

#completed
@router.post("/refresh", response_model=Token)
def refresh_token(body: TokenRefresh, db: Session = Depends(deps.get_db)):
    """Exchange a valid refresh token for a new token pair."""
    svc = AuthService(db)
    return svc.refresh_token(body.refresh_token)

#completed
@router.post("/change-password")
def change_password(
    body: ChangePassword,
    background_tasks: BackgroundTasks,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Change password for the authenticated user."""
    svc = AuthService(db)
    return svc.change_password(current_user, body.current_password, body.new_password, background_tasks)

@router.post("/logout")
def logout():
    """
    Client-side logout — instruct the client to discard tokens.

    Server-side token revocation can be added later with a token blacklist.
    """
    return {"detail": "Successfully logged out. Please discard your tokens."}
