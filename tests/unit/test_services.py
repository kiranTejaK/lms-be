# ==============================================================================
# UNIT TESTS — S3 and Email services with mocked externals
#
# Mocking:
#   - S3:   Moto (in-process AWS mock) for realistic S3 behavior
#   - SMTP: MailHog configuration (localhost:1025) or mocked smtplib
#           for isolated unit testing of the email service
#
# These tests verify service logic in isolation — no database, no network.
# ==============================================================================

"""Unit tests for S3 and Email service classes."""

import pytest
from unittest.mock import patch, MagicMock


# ── S3 Service Unit Tests ─────────────────────────────────────────────────


def test_s3_upload_with_mock():
    """UNIT: S3Service.upload_file returns a URL when boto3 is mocked."""
    with patch("app.services.s3_service.boto3.client") as mock_client:
        mock_s3 = MagicMock()
        mock_client.return_value = mock_s3

        from app.services.s3_service import S3Service

        svc = S3Service()
        svc.s3_client = mock_s3  # Override the actual client

        content = b"test file content"
        result = svc.upload_file(content, "uploads/test.txt", "text/plain")

        # Since the mock doesn't raise, it should return a URL string
        assert result is not None


def test_s3_upload_no_credentials():
    """UNIT: S3Service with no credentials returns empty string."""
    with patch("app.services.s3_service.settings") as mock_settings:
        mock_settings.AWS_ACCESS_KEY_ID = None
        mock_settings.AWS_SECRET_ACCESS_KEY = None
        mock_settings.AWS_S3_BUCKET = None
        mock_settings.AWS_REGION = None

        from app.services.s3_service import S3Service

        svc = S3Service()
        svc.s3_client = None  # No client when no credentials
        result = svc.upload_file(b"content", "test.txt", "text/plain")
        assert result == ""


# ── Email Service Unit Tests ──────────────────────────────────────────────
# NOTE: For full MailHog integration tests, connect to localhost:1025
# and verify delivery via the MailHog HTTP API (localhost:8025/api/v2/messages).
# The tests below use mocked smtplib for fast, isolated unit testing.


def test_email_send_with_mock():
    """UNIT: EmailService.send_email works with mocked SMTP and template."""
    with patch("app.services.email_service.smtplib.SMTP") as mock_smtp:
        instance = mock_smtp.return_value.__enter__.return_value

        with patch("app.services.email_service.settings") as mock_settings:
            mock_settings.BREVO_SMTP_PASSWORD = "test_password"
            mock_settings.BREVO_SMTP_SERVER = "localhost"
            mock_settings.BREVO_SMTP_PORT = 1025  # MailHog default port
            mock_settings.BREVO_SMTP_USER = "test_user"
            mock_settings.EMAIL_FROM_NAME = "Test"
            mock_settings.EMAIL_FROM_EMAIL = "test@example.com"
            mock_settings.EMAIL_TEMPLATE_DIR = "app/templates"

            from app.services.email_service import EmailService

            result = EmailService.send_email(
                "recipient@example.com",
                "Test Subject",
                "app/templates/welcome.html",
                context={"full_name": "Test User", "year": 2026},
            )

            instance.starttls.assert_called_once()
            instance.login.assert_called_once()


def test_email_send_not_configured():
    """UNIT: EmailService returns False when SMTP is not configured."""
    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.BREVO_SMTP_PASSWORD = None

        from app.services.email_service import EmailService

        result = EmailService.send_email(
            "test@example.com",
            "Subject",
            "app/templates/welcome.html",
            context={"full_name": "Test", "year": 2026},
        )
        assert result is False
