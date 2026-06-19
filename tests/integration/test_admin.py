# ==============================================================================
# INTEGRATION TESTS — Admin endpoint tests via FastAPI TestClient
#
# Mocking: Real DB (SQLite), real JWT tokens, real structlog.
# Tests verify role-based access control (admin vs non-admin vs unauthenticated).
# ==============================================================================

"""Admin endpoint tests."""

from app.core.config import settings

PREFIX = f"/{settings.APP_PREFIX}/v1"


def test_dashboard_stats_admin(client, admin_headers):
    """INTEGRATION: Admin can access dashboard stats."""
    resp = client.get(f"{PREFIX}/admin/dashboard", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_users" in data
    assert "total_courses" in data
    assert "total_enrollments" in data
    assert "total_categories" in data
    assert "total_lessons" in data


def test_dashboard_stats_non_admin(client, auth_headers):
    """INTEGRATION: Non-admin users are rejected from admin endpoints (403)."""
    resp = client.get(f"{PREFIX}/admin/dashboard", headers=auth_headers)
    assert resp.status_code == 403


def test_dashboard_stats_unauthenticated(client):
    """INTEGRATION: Unauthenticated requests are rejected (401)."""
    resp = client.get(f"{PREFIX}/admin/dashboard")
    assert resp.status_code == 401


def test_list_failed_tasks_admin(client, admin_headers):
    """INTEGRATION: Admin can list failed tasks."""
    resp = client.get(f"{PREFIX}/admin/failed-tasks", headers=admin_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_failed_tasks_non_admin(client, auth_headers):
    """INTEGRATION: Non-admin users are rejected from failed tasks endpoint (403)."""
    resp = client.get(f"{PREFIX}/admin/failed-tasks", headers=auth_headers)
    assert resp.status_code == 403
