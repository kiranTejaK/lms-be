"""
INTEGRATION TEST - Moto functional S3 verification.

This test connects to a real Moto server (Docker on localhost:5000)
and verifies that the file was actually uploaded and exists.

Unlike the unit tests in test_services.py, these do NOT mock boto3.client.
"""

import io
from unittest.mock import patch

import pytest

from app.services.s3_service import S3Service


@pytest.mark.integration
def test_functional_s3_upload_and_delete(s3_integration_client):
    """
    FUNCTIONAL: Upload a file via S3Service and verify it exists in Moto.
    """
    # 1. Arrange - Override settings to point to local Moto
    with patch("app.services.s3_service.settings") as mock_settings:
        mock_settings.AWS_ACCESS_KEY_ID = "testing"
        mock_settings.AWS_SECRET_ACCESS_KEY = "testing"
        mock_settings.AWS_REGION = "us-east-1"
        mock_settings.AWS_S3_BUCKET = "test-bucket"
        mock_settings.AWS_ENDPOINT_URL = "http://localhost:5000"

        svc = S3Service()
        content = b"Integration test file content"
        file_obj = io.BytesIO(content)
        object_name = "integration-tests/test_file.txt"

        # 2. Act - Upload
        url = svc.upload_file(file_obj, object_name, "text/plain")

        # 3. Assert - Check result from service
        assert url != ""
        assert "test-bucket" in url
        assert object_name in url

        # 4. Verify - Check real boto client for existence
        resp = s3_integration_client.get_object(Bucket="test-bucket", Key=object_name)
        downloaded_content = resp["Body"].read()
        assert downloaded_content == content

        # 5. Act - Delete
        success = svc.delete_file(object_name)
        assert success is True

        # 6. Verify - Check it's gone
        with pytest.raises(Exception):
            s3_integration_client.get_object(Bucket="test-bucket", Key=object_name)

def test_s3_mock_vs_real_comparison():
    """
    Informational test showing the difference between mocking and integration.
    """
    print("\n--- MOCK VS REAL S3 COMPARISON ---")
    print("MOCK: tests/test_services.py -> test_s3_upload_with_mock (fast, in-memory Moto decorator)")
    print("REAL: tests/test_integration_s3.py -> test_functional_s3_upload_and_delete (slow, hits real container)")
    assert True
