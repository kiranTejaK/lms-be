from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel
from app.db.mixins import IDMixin, TimeStampMixin

if TYPE_CHECKING:
    from .course import Course, Enrollment

user_roles = Table(
    'user_roles',
    BaseModel.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True)
)

class User(BaseModel, IDMixin, TimeStampMixin):
    __tablename__ = 'users'
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    roles: Mapped[List["Role"]] = relationship("Role", secondary=user_roles, back_populates="users")
    profile: Mapped[Optional["UserProfile"]] = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    instructor: Mapped[Optional["Instructor"]] = relationship("Instructor", back_populates="user", uselist=False, cascade="all, delete-orphan")
    enrollments: Mapped[List["Enrollment"]] = relationship("Enrollment", back_populates="user", cascade="all, delete-orphan")

class Role(BaseModel, IDMixin, TimeStampMixin):
    __tablename__ = 'roles'
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    users: Mapped[List["User"]] = relationship("User", secondary=user_roles, back_populates="roles")

class UserProfile(BaseModel, IDMixin, TimeStampMixin):
    __tablename__ = 'user_profile'
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    bio: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id', ondelete='CASCADE'), unique=True, index=True, nullable=False)
    user: Mapped["User"] = relationship("User", back_populates="profile")

class Instructor(BaseModel, IDMixin, TimeStampMixin):
    __tablename__ = 'instructors'
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    specialization: Mapped[str] = mapped_column(String(255), nullable=False)
    rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id', ondelete='CASCADE'), unique=True, index=True, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="instructor")
    courses: Mapped[List["Course"]] = relationship("Course", back_populates="instructor")
