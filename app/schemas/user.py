"""User-related Pydantic schemas for request/response serialization."""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr

# ── Role ─────────────────────────────────────────────────────────────────

class RoleBase(BaseModel):
    name: str

class RoleCreate(RoleBase):
    pass

class RoleResponse(RoleBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# ── User Profile ─────────────────────────────────────────────────────────

class UserProfileBase(BaseModel):
    full_name: str
    bio: Optional[str] = None
    avatar_url: Optional[str] = None

class UserProfileCreate(UserProfileBase):
    user_id: int

class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    bio: Optional[str] = None

class UserProfileResponse(UserProfileBase):
    id: int
    user_id: int
    model_config = ConfigDict(from_attributes=True)


# ── Instructor ───────────────────────────────────────────────────────────

class InstructorBase(BaseModel):
    bio: Optional[str] = None
    specialization: str
    rating: float = 0.0

class InstructorCreate(InstructorBase):
    user_id: int

class InstructorUpdate(BaseModel):
    bio: Optional[str] = None
    specialization: Optional[str] = None
    rating: Optional[float] = None

class InstructorResponse(InstructorBase):
    id: int
    user_id: int
    model_config = ConfigDict(from_attributes=True)


# ── User ─────────────────────────────────────────────────────────────────

class UserBase(BaseModel):
    email: EmailStr
    username: str

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    """Partial update schema — all fields optional."""
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    is_active: Optional[bool] = None

class UserResponse(UserBase):
    id: int
    is_active: bool
    roles: List[RoleResponse] = []
    model_config = ConfigDict(from_attributes=True)

class UserListResponse(BaseModel):
    """Paginated user listing."""
    users: List[UserResponse]
    total: int


# ── Authentication ───────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenRefresh(BaseModel):
    refresh_token: str

class ChangePassword(BaseModel):
    current_password: str
    new_password: str

class RoleAssign(BaseModel):
    user_id: int
    role_id: int
