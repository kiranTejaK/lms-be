import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture(autouse=True)
def mock_redis():
    """Mock redis_client in app.core.redis for all unit tests."""
    with patch("app.core.redis.redis_client") as mock:
        mock.get.return_value = None
        mock.setex.return_value = True
        mock.keys.return_value = []
        mock.delete.return_value = 0
        yield mock
