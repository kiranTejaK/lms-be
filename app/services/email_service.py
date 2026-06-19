import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

import structlog
from jinja2 import Template

from app.core.config import settings

logger = structlog.get_logger(__name__)

_SMTP_TIMEOUT: int = 30

class EmailService:
    @staticmethod
    def _build_message(to_email: str, subject: str, html_content: str) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_EMAIL}>"
        msg["To"] = to_email
        msg.attach(MIMEText(html_content, "html"))
        return msg

    @staticmethod
    def _send(msg: MIMEMultipart) -> bool:
        try:
            with smtplib.SMTP(settings.BREVO_SMTP_SERVER, settings.BREVO_SMTP_PORT, timeout=_SMTP_TIMEOUT,) as server:
                if settings.EMAIL_USE_TLS:
                    server.starttls()
                server.login(settings.BREVO_SMTP_USER or "", settings.BREVO_SMTP_PASSWORD)
                server.send_message(msg)
            return True
        except smtplib.SMTPAuthenticationError:
            logger.error("smtp_auth_failed", server=settings.BREVO_SMTP_SERVER)
            return False
        except (smtplib.SMTPException, socket.timeout, OSError) as exc:
            logger.error("smtp_send_failed", error=str(exc))
            return False

    @staticmethod
    def send_email(to_email: str, subject: str, template_path: str, context: Optional[Dict[str, Any]] = None,) -> bool:
        if not settings.BREVO_SMTP_PASSWORD:
            logger.warning("smtp_not_configured", to_email=to_email)
            return False

        context = context or {}

        try:
            with open(template_path, "r", encoding="utf-8") as fh:
                html_content = Template(fh.read()).render(**context)
        except FileNotFoundError:
            logger.error("email_template_not_found", path=template_path)
            return False
        except Exception as exc:
            logger.error("email_template_render_failed", error=str(exc))
            return False

        msg = EmailService._build_message(to_email, subject, html_content)
        success = EmailService._send(msg)

        if success:
            logger.info("email_sent", to_email=to_email, subject=subject)
        else:
            logger.error("email_send_failed", to_email=to_email)

        return success

# """
# Email service using SMTP with Jinja2 HTML templates.

# All emails are rendered from templates on disk — no raw HTML is accepted.
# This enforces visual consistency and makes email content auditable.

# All operations are synchronous.  TLS is enforced via ``starttls()``.
# SMTP server, port, and credentials are loaded from ``app.core.config``.

# The service degrades gracefully: if SMTP is not configured (no password),
# methods return ``False`` and log a warning rather than raising.
# """

# import smtplib
# import socket
# from email.mime.text import MIMEText
# from email.mime.multipart import MIMEMultipart
# from typing import Dict, Any, Optional

# from jinja2 import Template

# import structlog

# from app.core.config import settings

# logger = structlog.get_logger(__name__)

# # Connection timeout for the SMTP server (seconds).
# _SMTP_TIMEOUT: int = 30


# class EmailService:
#     """
#     Synchronous, template-only email service backed by an SMTP relay.

#     Usage::

#         EmailService.send_email(
#             to_email="user@example.com",
#             subject="Welcome!",
#             template_path="app/templates/welcome.html",
#             context={"full_name": "John", "year": 2026},
#         )
#     """

#     # ── Internal Helpers ──────────────────────────────────────────────

#     @staticmethod
#     def _build_message(to_email: str, subject: str, html_content: str) -> MIMEMultipart:
#         """Build a MIME message with the platform's standard From header."""
#         msg = MIMEMultipart("alternative")
#         msg["Subject"] = subject
#         msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_EMAIL}>"
#         msg["To"] = to_email
#         msg.attach(MIMEText(html_content, "html"))
#         return msg

#     @staticmethod
#     def _send(msg: MIMEMultipart) -> bool:
#         """Open an SMTP connection, authenticate, and send the message."""
#         try:
#             with smtplib.SMTP(
#                 settings.BREVO_SMTP_SERVER,
#                 settings.BREVO_SMTP_PORT,
#                 timeout=_SMTP_TIMEOUT,
#             ) as server:
#                 server.starttls()
#                 server.login(settings.BREVO_SMTP_USER or "", settings.BREVO_SMTP_PASSWORD)
#                 server.send_message(msg)
#             return True
#         except smtplib.SMTPAuthenticationError:
#             logger.error("smtp_auth_failed", server=settings.BREVO_SMTP_SERVER)
#             return False
#         except (smtplib.SMTPException, socket.timeout, OSError) as exc:
#             logger.error("smtp_send_failed", error=str(exc))
#             return False

#     # ── Public API ────────────────────────────────────────────────────

#     @staticmethod
#     def send_email(
#         to_email: str,
#         subject: str,
#         template_path: str,
#         context: Optional[Dict[str, Any]] = None,
#     ) -> bool:
#         """
#         Render an HTML template and send it via SMTP.

#         Args:
#             to_email: Recipient address.
#             subject: Email subject line.
#             template_path: Path to a Jinja2 HTML template on disk.
#             context: Variables passed to ``Template.render()``.

#         Returns:
#             ``True`` on success, ``False`` on any failure.
#         """
#         if not settings.BREVO_SMTP_PASSWORD:
#             logger.warning("smtp_not_configured", to_email=to_email)
#             return False

#         context = context or {}

#         try:
#             with open(template_path, "r", encoding="utf-8") as fh:
#                 html_content = Template(fh.read()).render(**context)
#         except FileNotFoundError:
#             logger.error("email_template_not_found", path=template_path)
#             return False
#         except Exception as exc:
#             logger.error("email_template_render_failed", error=str(exc))
#             return False

#         msg = EmailService._build_message(to_email, subject, html_content)
#         success = EmailService._send(msg)

#         if success:
#             logger.info("email_sent", to_email=to_email, subject=subject)
#         else:
#             logger.error("email_send_failed", to_email=to_email)

#         return success
