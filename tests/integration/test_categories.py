# ==============================================================================
# INTEGRATION TESTS — Category CRUD endpoint tests via FastAPI TestClient
#
# Mocking: Real DB (SQLite), real Redis, real structlog.
# The last test (duplicate category) also serves as a REGRESSION test for
# the unique constraint enforcement.
# ==============================================================================

"""Category endpoint tests."""

import uuid
from app.core.config import settings

PREFIX = f"/{settings.APP_PREFIX}/v1"


def test_create_category(client):
    """INTEGRATION: Create a category via POST endpoint."""
    name = f"Category_{uuid.uuid4().hex[:8]}"
    resp = client.post(f"{PREFIX}/categories/", json={"name": name})
    assert resp.status_code == 200
    assert resp.json()["name"] == name


def test_list_categories(client):
    """INTEGRATION: GET /categories/ returns a list."""
    resp = client.get(f"{PREFIX}/categories/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_category(client, test_category):
    """INTEGRATION: GET /categories/{id} returns the correct category."""
    resp = client.get(f"{PREFIX}/categories/{test_category.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == test_category.id


def test_get_category_not_found(client):
    """INTEGRATION: GET /categories/99999 returns 404."""
    resp = client.get(f"{PREFIX}/categories/99999")
    assert resp.status_code == 404


def test_update_category(client, test_category):
    """INTEGRATION: PUT /categories/{id} updates the category name."""
    resp = client.put(
        f"{PREFIX}/categories/{test_category.id}",
        json={"name": "UpdatedName"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "UpdatedName"


def test_delete_category(client, test_category):
    """INTEGRATION: DELETE /categories/{id} removes the category."""
    resp = client.delete(f"{PREFIX}/categories/{test_category.id}")
    assert resp.status_code == 200


# ==============================================================================
# REGRESSION TEST — Duplicate category name constraint
# Ensures the unique constraint on category name is properly enforced.
# ==============================================================================

def test_create_duplicate_category(client, test_category):
    """REGRESSION: Creating a category with a duplicate name returns 409."""
    resp = client.post(
        f"{PREFIX}/categories/", json={"name": test_category.name}
    )
    assert resp.status_code == 409
