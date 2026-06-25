"""Course-related Pydantic schemas for request/response serialization."""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict

# ── Category ─────────────────────────────────────────────────────────────

class CategoryBase(BaseModel):
    name: str

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseModel):
    name: Optional[str] = None

class CategoryResponse(CategoryBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# ── Course ───────────────────────────────────────────────────────────────

class CourseBase(BaseModel):
    title: str
    description: Optional[str] = None
    category_id: Optional[int] = None
    instructor_id: Optional[int] = None
    max_students: int = 100

class CourseCreate(CourseBase):
    pass

class CourseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    instructor_id: Optional[int] = None
    max_students: Optional[int] = None

class CourseResponse(CourseBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# ── Lesson ───────────────────────────────────────────────────────────────

class LessonBase(BaseModel):
    title: str
    content: str
    lesson_order: int

class LessonCreate(LessonBase):
    course_id: int

class LessonUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    lesson_order: Optional[int] = None

class LessonResponse(LessonBase):
    id: int
    course_id: int
    model_config = ConfigDict(from_attributes=True)


# ── Enrollment ───────────────────────────────────────────────────────────

class EnrollmentCreate(BaseModel):
    course_id: int

class EnrollmentUpdate(BaseModel):
    progress: Optional[int] = None
    completed: Optional[bool] = None

class EnrollmentResponse(BaseModel):
    id: int
    progress: int
    completed: bool
    user_id: int
    course_id: int
    model_config = ConfigDict(from_attributes=True)


# ── Nested / Detailed Responses ──────────────────────────────────────────

from app.schemas.user import InstructorResponse  # noqa: E402


class CourseDetailedResponse(CourseResponse):
    """Course with eager-loaded relations for dashboard views."""
    category: Optional[CategoryResponse] = None
    instructor: Optional[InstructorResponse] = None
    lessons: List[LessonResponse] = []
    model_config = ConfigDict(from_attributes=True)


# ── Dashboard / Stats ───────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_users: int
    total_courses: int
    total_enrollments: int
    total_categories: int
    total_lessons: int
