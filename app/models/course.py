from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel
from app.db.mixins import IDMixin, TimeStampMixin

if TYPE_CHECKING:
    from .user import Instructor, User

class Category(BaseModel, IDMixin, TimeStampMixin):
    __tablename__ = 'categories'
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    courses: Mapped[List["Course"]] = relationship("Course", back_populates="category")

class Course(BaseModel, IDMixin, TimeStampMixin):
    __tablename__ = 'courses'
    title: Mapped[str] = mapped_column(String(155), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('categories.id', ondelete='SET NULL'), nullable=True)
    instructor_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('instructors.id', ondelete='SET NULL'), nullable=True)
    max_students: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    category: Mapped[Optional["Category"]] = relationship("Category", back_populates="courses")
    instructor: Mapped[Optional["Instructor"]] = relationship("Instructor", back_populates="courses")
    lessons: Mapped[List["Lesson"]] = relationship("Lesson", back_populates="course", cascade="all, delete-orphan")
    enrollments: Mapped[List["Enrollment"]] = relationship("Enrollment", back_populates="course", cascade="all, delete-orphan")

class Lesson(BaseModel, IDMixin, TimeStampMixin):
    __tablename__ = 'lessons'
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    lesson_order: Mapped[int] = mapped_column(Integer, nullable=False)
    course_id: Mapped[int] = mapped_column(Integer, ForeignKey('courses.id', ondelete='CASCADE'), nullable=False)

    course: Mapped["Course"] = relationship("Course", back_populates="lessons")

class Enrollment(BaseModel, IDMixin, TimeStampMixin):
    __tablename__ = 'enrollments'
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    course_id: Mapped[int] = mapped_column(Integer, ForeignKey('courses.id', ondelete='CASCADE'), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="enrollments")
    course: Mapped["Course"] = relationship("Course", back_populates="enrollments")

    __table_args__ = (UniqueConstraint('user_id', 'course_id', name='uq_enrollments_user_id'),)
