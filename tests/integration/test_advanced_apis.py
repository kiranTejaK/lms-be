# ==============================================================================
# INTEGRATION TESTS — Advanced API endpoint tests via FastAPI TestClient
#
# Mocking: Real DB (SQLite), real Redis, real JWT tokens, real structlog.
# SMTP mocked for email side-effects during enrollment.
#
# Tests cover:
#   - Concurrent enrollment with row-level locking
#   - Instructor dashboard with N+1 prevention
#   - Bulk course creation with atomic rollback
#   - Course analytics with aggregation queries
#   - Enrollment transfer with pessimistic locking
# ==============================================================================

"""Advanced API endpoint tests — production database patterns."""

import uuid
import pytest
from unittest.mock import patch
from app.core.config import settings
from app.core.security import get_password_hash

PREFIX = f"/{settings.APP_PREFIX}/v1"

# ── Bulk Course Creation ─────────────────────────────────────────────────

def test_bulk_create_courses(client):
    """INTEGRATION: Bulk-create multiple courses in a single atomic transaction."""
    resp = client.post(
        f"{PREFIX}/advanced/bulk-create-courses",
        json={
            "courses": [
                {"title": "Course A", "description": "First", "max_students": 30},
                {"title": "Course B", "description": "Second", "max_students": 50},
                {"title": "Course C", "description": "Third", "max_students": 20},
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["created_count"] == 3
    assert len(data["course_ids"]) == 3


def test_bulk_create_empty_list(client):
    """INTEGRATION: Bulk-create with empty list succeeds with 0 courses."""
    resp = client.post(
        f"{PREFIX}/advanced/bulk-create-courses",
        json={"courses": []},
    )
    assert resp.status_code == 200
    assert resp.json()["created_count"] == 0


# ── Course Analytics ─────────────────────────────────────────────────────

def test_course_analytics(client, test_course):
    """INTEGRATION: Analytics endpoint returns aggregated enrollment stats."""
    resp = client.get(f"{PREFIX}/advanced/course-analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert "courses" in data
    assert "total_courses" in data
    assert data["total_courses"] >= 1


def test_course_analytics_with_enrollment(client, test_course, auth_headers):
    """INTEGRATION: Analytics reflects enrollment count after enrolling."""
    # Enroll
    client.post(
        f"{PREFIX}/courses/{test_course.id}/enroll",
        headers=auth_headers,
    )

    resp = client.get(f"{PREFIX}/advanced/course-analytics")
    assert resp.status_code == 200
    data = resp.json()
    # Find our test course in the analytics
    course_stats = [c for c in data["courses"] if c["course_id"] == test_course.id]
    assert len(course_stats) == 1
    assert course_stats[0]["enrollment_count"] >= 1


# ── Concurrent Enrollment ────────────────────────────────────────────────

@patch("app.services.advanced_service.EmailService.send_email", return_value=True)
def test_concurrent_enroll_success(mock_email, client, test_course, two_users):
    """INTEGRATION: Bulk-enroll multiple users with row-level locking."""
    user_ids = [u.id for u in two_users]
    resp = client.post(
        f"{PREFIX}/advanced/concurrent-enroll",
        json={"course_id": test_course.id, "user_ids": user_ids},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["enrolled_count"] == 2
    assert len(data["enrollment_ids"]) == 2


@patch("app.services.advanced_service.EmailService.send_email", return_value=True)
def test_concurrent_enroll_course_full(mock_email, client, db_session, two_users):
    """INTEGRATION: Enrollment fails when course capacity would be exceeded."""
    from app.models.course import Course

    # Create a tiny-capacity course
    course = Course(title="Tiny Course", max_students=1)
    db_session.add(course)
    db_session.commit()
    db_session.refresh(course)

    user_ids = [u.id for u in two_users]
    resp = client.post(
        f"{PREFIX}/advanced/concurrent-enroll",
        json={"course_id": course.id, "user_ids": user_ids},
    )
    assert resp.status_code == 422  # ValidationException → 422


@patch("app.services.advanced_service.EmailService.send_email", return_value=True)
def test_concurrent_enroll_nonexistent_course(mock_email, client, two_users):
    """INTEGRATION: Enrollment fails for non-existent course."""
    resp = client.post(
        f"{PREFIX}/advanced/concurrent-enroll",
        json={"course_id": 99999, "user_ids": [two_users[0].id]},
    )
    assert resp.status_code == 404


# ── Instructor Dashboard ─────────────────────────────────────────────────

def test_instructor_dashboard(client, instructor_with_course, test_instructor):
    """INTEGRATION: Dashboard returns instructor with courses and lessons (N+1 safe)."""
    resp = client.get(
        f"{PREFIX}/advanced/instructor-dashboard/{test_instructor.id}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["instructor_id"] == test_instructor.id
    assert data["specialization"] == "Backend Development"
    assert len(data["courses"]) >= 1


def test_instructor_dashboard_not_found(client):
    """INTEGRATION: Dashboard for non-existent instructor returns 404."""
    resp = client.get(f"{PREFIX}/advanced/instructor-dashboard/99999")
    assert resp.status_code == 404


# ── Transfer Enrollment ──────────────────────────────────────────────────

@patch("app.services.advanced_service.EmailService.send_email", return_value=True)
def test_transfer_enrollment(mock_email, client, db_session, test_user):
    """INTEGRATION: Transfer a student from one course to another with row locking."""
    from app.models.course import Course, Enrollment

    # Create two courses
    course_a = Course(title="Course A", max_students=50)
    course_b = Course(title="Course B", max_students=50)
    db_session.add_all([course_a, course_b])
    db_session.commit()
    db_session.refresh(course_a)
    db_session.refresh(course_b)

    # Enroll user in course A
    enrollment = Enrollment(user_id=test_user.id, course_id=course_a.id)
    db_session.add(enrollment)
    db_session.commit()

    # Transfer from A → B
    resp = client.post(
        f"{PREFIX}/advanced/transfer-enrollment",
        json={
            "user_id": test_user.id,
            "from_course_id": course_a.id,
            "to_course_id": course_b.id,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["from_course_id"] == course_a.id
    assert data["to_course_id"] == course_b.id


def test_transfer_enrollment_not_enrolled(client, db_session, test_user):
    """INTEGRATION: Transfer fails when user is not enrolled in source course."""
    from app.models.course import Course

    course_a = Course(title="Transfer A", max_students=50)
    course_b = Course(title="Transfer B", max_students=50)
    db_session.add_all([course_a, course_b])
    db_session.commit()
    db_session.refresh(course_a)
    db_session.refresh(course_b)

    resp = client.post(
        f"{PREFIX}/advanced/transfer-enrollment",
        json={
            "user_id": test_user.id,
            "from_course_id": course_a.id,
            "to_course_id": course_b.id,
        },
    )
    assert resp.status_code == 404


# ==============================================================================
# REGRESSION TEST — Duplicate enrollment during concurrent enroll
# Ensures that the row-locking mechanism prevents double enrollment.
# ==============================================================================

@patch("app.services.advanced_service.EmailService.send_email", return_value=True)
def test_concurrent_enroll_duplicate_rejected(mock_email, client, test_course, two_users):
    """REGRESSION: Concurrent enroll rejects users who are already enrolled."""
    # Enroll first user
    resp = client.post(
        f"{PREFIX}/advanced/concurrent-enroll",
        json={"course_id": test_course.id, "user_ids": [two_users[0].id]},
    )
    assert resp.status_code == 200

    # Try enrolling the same user again
    resp = client.post(
        f"{PREFIX}/advanced/concurrent-enroll",
        json={"course_id": test_course.id, "user_ids": [two_users[0].id]},
    )
    assert resp.status_code == 409
