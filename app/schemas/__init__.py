"""Re-export all schemas for convenient imports."""

from .user import (
    UserBase, UserCreate, UserUpdate, UserResponse, UserListResponse,
    Token, TokenRefresh, ChangePassword,
    RoleBase, RoleCreate, RoleResponse, RoleAssign,
    UserProfileBase, UserProfileCreate, UserProfileUpdate, UserProfileResponse,
    InstructorBase, InstructorCreate, InstructorUpdate, InstructorResponse,
)
from .course import (
    CategoryBase, CategoryCreate, CategoryUpdate, CategoryResponse,
    CourseBase, CourseCreate, CourseUpdate, CourseResponse, CourseDetailedResponse,
    LessonBase, LessonCreate, LessonUpdate, LessonResponse,
    EnrollmentCreate, EnrollmentUpdate, EnrollmentResponse,
    DashboardStats,
)
from .failed_task import FailedTaskBase, FailedTaskCreate, FailedTaskResponse
