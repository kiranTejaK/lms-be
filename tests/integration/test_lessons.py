# ==============================================================================
# INTEGRATION TESTS — Lesson CRUD endpoint tests via FastAPI TestClient
#
# Mocking: Real DB (SQLite), real Redis, real structlog.
# Tests CRUD lifecycle and FK constraint validation (course must exist).
# ==============================================================================

"""Lesson endpoint tests."""

from app.core.config import settings

PREFIX = f"/{settings.APP_PREFIX}/v1"


def test_create_lesson(client, test_course):
    """INTEGRATION: Create a lesson linked to an existing course."""
    resp = client.post(
        f"{PREFIX}/lessons/",
        json={
            "title": "Intro to APIs",
            "content": "APIs are awesome",
            "lesson_order": 1,
            "course_id": test_course.id,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Intro to APIs"


def test_create_lesson_course_not_found(client):
    """INTEGRATION: Creating a lesson for non-existent course returns 404."""
    resp = client.post(
        f"{PREFIX}/lessons/",
        json={
            "title": "Orphan Lesson",
            "content": "No course",
            "lesson_order": 1,
            "course_id": 99999,
        },
    )
    assert resp.status_code == 404


def test_list_lessons_by_course(client, test_lesson):
    """INTEGRATION: Listing lessons by course returns at least the fixture lesson."""
    resp = client.get(f"{PREFIX}/lessons/by-course/{test_lesson.course_id}")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


def test_get_lesson(client, test_lesson):
    """INTEGRATION: GET /lessons/{id} returns the correct lesson."""
    resp = client.get(f"{PREFIX}/lessons/{test_lesson.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == test_lesson.id


def test_update_lesson(client, test_lesson):
    """INTEGRATION: PUT /lessons/{id} updates lesson fields."""
    resp = client.put(
        f"{PREFIX}/lessons/{test_lesson.id}",
        json={"title": "Updated Lesson Title"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Lesson Title"


def test_delete_lesson(client, test_lesson):
    """INTEGRATION: DELETE /lessons/{id} removes the lesson."""
    resp = client.delete(f"{PREFIX}/lessons/{test_lesson.id}")
    assert resp.status_code == 200


def test_get_lesson_not_found(client):
    """INTEGRATION: GET /lessons/99999 returns 404."""
    resp = client.get(f"{PREFIX}/lessons/99999")
    assert resp.status_code == 404
