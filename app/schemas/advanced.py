"""Pydantic schemas for advanced API endpoints."""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict

# ── Requests ─────────────────────────────────────────────────────────────

class BulkEnrollRequest(BaseModel):
    """Enroll multiple users in a single course atomically."""
    course_id: int
    user_ids: List[int]


class BulkCourseCreateItem(BaseModel):
    """Single course payload within a bulk-create request."""
    title: str
    description: Optional[str] = None
    category_id: Optional[int] = None
    instructor_id: Optional[int] = None
    max_students: int = 100


class BulkCourseCreateRequest(BaseModel):
    """Create multiple courses in a single atomic transaction."""
    courses: List[BulkCourseCreateItem]


class TransferEnrollmentRequest(BaseModel):
    """Transfer a student from one course to another."""
    user_id: int
    from_course_id: int
    to_course_id: int


# ── Responses ────────────────────────────────────────────────────────────

class BulkEnrollResponse(BaseModel):
    status: str
    enrolled_count: int
    enrollment_ids: List[int]


class BulkCourseCreateResponse(BaseModel):
    status: str
    created_count: int
    course_ids: List[int]


class TransferEnrollmentResponse(BaseModel):
    status: str
    new_enrollment_id: int
    from_course_id: int
    to_course_id: int


class CourseAnalyticsItem(BaseModel):
    course_id: int
    course_title: str
    enrollment_count: int
    completion_rate: float
    avg_progress: float
    model_config = ConfigDict(from_attributes=True)


class CourseAnalyticsResponse(BaseModel):
    courses: List[CourseAnalyticsItem]
    total_courses: int


class LessonSummary(BaseModel):
    id: int
    title: str
    lesson_order: int
    model_config = ConfigDict(from_attributes=True)


class CourseSummary(BaseModel):
    id: int
    title: str
    enrollment_count: int
    lessons: List[LessonSummary] = []
    model_config = ConfigDict(from_attributes=True)


class InstructorDashboardResponse(BaseModel):
    instructor_id: int
    specialization: str
    rating: float
    total_students: int
    courses: List[CourseSummary]
