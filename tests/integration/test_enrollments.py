# ==============================================================================
# INTEGRATION TESTS — Enrollment endpoint tests via FastAPI TestClient
#
# Mocking: Real DB (SQLite), real Redis, real JWT tokens, real structlog.
# Tests the enrollment lifecycle: enroll → list → update → unenroll.
# The last test is a REGRESSION test for the double-enrollment bug.
# ==============================================================================

"""Enrollment endpoint tests."""

from app.core.config import settings

PREFIX = f"/{settings.APP_PREFIX}/v1"


def test_enroll_and_list_enrollments(client, test_course, auth_headers, test_user):
    """INTEGRATION: Enroll in a course, then list enrollments for the user."""
    # Enroll
    resp = client.post(
        f"{PREFIX}/courses/{test_course.id}/enroll",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    enrollment_id = resp.json()["enrollment_id"]

    # List user enrollments
    resp = client.get(f"{PREFIX}/enrollments/user/{test_user.id}")
    assert resp.status_code == 200
    enrollments = resp.json()
    assert len(enrollments) >= 1

    # List course enrollments
    resp = client.get(f"{PREFIX}/enrollments/course/{test_course.id}")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_update_enrollment_progress(client, test_course, auth_headers, test_user):
    """INTEGRATION: Enroll then update progress to 50%."""
    # Enroll first
    resp = client.post(
        f"{PREFIX}/courses/{test_course.id}/enroll",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    enrollment_id = resp.json()["enrollment_id"]

    # Update progress
    resp = client.put(
        f"{PREFIX}/enrollments/{enrollment_id}",
        json={"progress": 50, "completed": False},
    )
    assert resp.status_code == 200
    assert resp.json()["progress"] == 50


def test_unenroll(client, test_course, auth_headers, test_user):
    """INTEGRATION: Enroll then unenroll successfully."""
    resp = client.post(
        f"{PREFIX}/courses/{test_course.id}/enroll",
        headers=auth_headers,
    )
    enrollment_id = resp.json()["enrollment_id"]

    resp = client.delete(
        f"{PREFIX}/enrollments/{enrollment_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200


# ==============================================================================
# REGRESSION TEST — Double enrollment prevention
# Previously, the system allowed duplicate enrollments for the same
# user + course combination, violating the unique constraint.
# ==============================================================================

def test_double_enrollment_rejected(client, test_course, auth_headers):
    """REGRESSION: Enrolling twice in the same course should fail with 409."""
    client.post(f"{PREFIX}/courses/{test_course.id}/enroll", headers=auth_headers)
    resp = client.post(f"{PREFIX}/courses/{test_course.id}/enroll", headers=auth_headers)
    assert resp.status_code == 409
