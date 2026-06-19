"""
API v1 router — registers all endpoint modules.

Total endpoints: 44 across 10 routers.
"""

from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth,
    courses,
    users,
    categories,
    lessons,
    enrollments,
    instructors,
    roles,
    admin,
    advanced_apis,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(courses.router, prefix="/courses", tags=["courses"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(lessons.router, prefix="/lessons", tags=["lessons"])
api_router.include_router(enrollments.router, prefix="/enrollments", tags=["enrollments"])
api_router.include_router(instructors.router, prefix="/instructors", tags=["instructors"])
api_router.include_router(roles.router, prefix="/roles", tags=["roles"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(advanced_apis.router, prefix="/advanced", tags=["advanced"])
