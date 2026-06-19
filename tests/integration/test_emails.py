"""
INTEGRATION TEST - MailHog functional email delivery verification.

This test connects to a real SMTP server (MailHog on localhost:1025)
and verifies that the email was actually delivered by querying the 
MailHog HTTP API (localhost:8025).

Unlike the unit tests in test_services.py, these do NOT mock smtplib.
"""

import pytest
from unittest.mock import patch
from app.services.email_service import EmailService
from app.core.config import settings

@pytest.mark.integration
def test_functional_email_delivery(mailhog_client):
    """
    FUNCTIONAL: Send an email via EmailService and verify delivery in MailHog.
    """
    # 1. Arrange - Override settings to point to local MailHog
    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.BREVO_SMTP_SERVER = "localhost"
        mock_settings.BREVO_SMTP_PORT = 1025
        mock_settings.BREVO_SMTP_USER = "test@example.com"
        mock_settings.BREVO_SMTP_PASSWORD = "testpassword"
        mock_settings.EMAIL_FROM_NAME = "Test Admin"
        mock_settings.EMAIL_FROM_EMAIL = "admin@test.com"
        mock_settings.EMAIL_TEMPLATE_DIR = "app/templates"

        recipient = "user@example.com"
        subject = "Integration Test Email"

        # 2. Act - Send the email
        success = EmailService.send_email(
            recipient_email=recipient,
            subject=subject,
            template_path="app/templates/welcome.html", # Assuming this exists
            context={"full_name": "Integration Tester", "year": 2026}
        )

        # 3. Assert - Check result from service
        assert success is True

        # 4. Verify - Check MailHog HTTP API for the message
        messages = mailhog_client.get_messages()
        total_msgs = messages.get("total", 0)
        assert total_msgs >= 1

        # Look for our specific email
        found = False
        for msg in messages.get("items", []):
            content = msg.get("Content", {})
            headers = content.get("Headers", {})
            if subject in headers.get("Subject", [None])[0]:
                found = True
                # Check recipient
                assert recipient in headers.get("To", [None])[0]
                break

        assert found, f"Email with subject '{subject}' not found in MailHog."

def test_mock_vs_real_comparison():
    """
    Informational test showing the difference between mocking and integration.
    This test is just for reference as requested by the user.
    """
    print("\n--- MOCK VS REAL COMPARISON ---")
    print("MOCK: tests/test_services.py -> test_email_send_with_mock (fast, no network)")
    print("REAL: tests/test_integration_emails.py -> test_functional_email_delivery (slow, hits real container)")
    assert True
