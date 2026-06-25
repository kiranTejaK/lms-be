# SMTP Email System

## Purpose

The email system sends transactional emails (welcome, password reset) via **SMTP** using the Brevo (formerly Sendinblue) relay.  Emails are rendered from Jinja2 HTML templates for consistent branding.

---

## Architecture Overview

```
Service Layer (e.g. AuthService after registration)
    └── EmailService.send_email(to, subject, template, context)
            ├── Jinja2 Template.render(**context) → HTML string
            └── smtplib.SMTP → starttls → login → send_message
```

All email logic lives in **`app/services/email_service.py`**.  Templates are stored in **`app/templates/`**.

---

## Implementation Details

### Internal Architecture

The service uses two internal helpers to eliminate code duplication:

```python
@staticmethod
def _build_message(to_email, subject, html_content) -> MIMEMultipart:
    """Build a MIME message with the standard From header."""
    ...

@staticmethod
def _send(msg) -> bool:
    """Open SMTP, authenticate, send, handle errors."""
    ...
```

### Available Methods

| Method | Description |
|---|---|
| `send_email(to, subject, template_path, context)` | Render a Jinja2 template and send |
| `send_raw_html_email(to, subject, html_content)` | Send pre-rendered HTML directly |
| `send_bulk_emails(to_list, subject, template, contexts)` | Send to multiple recipients |

### SMTP Connection

```python
with smtplib.SMTP(server, port, timeout=30) as server:
    server.starttls()   # Upgrade to TLS
    server.login(user, password)
    server.send_message(msg)
```

- **TLS enforced** — `starttls()` encrypts the connection before credentials are sent
- **Timeout** — 30-second connection timeout prevents hanging on unresponsive servers
- **Context manager** — ensures the connection is always closed, even on error

### Templates

Templates use Jinja2 syntax with variables:

```html
<h1>Welcome to Learning Platform!</h1>
<p>Hi {{ full_name }},</p>
```

Available templates:
| Template | Variables | Purpose |
|---|---|---|
| `welcome.html` | `full_name`, `year` | New user registration |
| `password_reset.html` | `full_name`, `reset_link`, `year` | Password reset request |

---

## Configuration Variables

| Variable | Default | Description |
|---|---|---|
| `BREVO_SMTP_SERVER` | `smtp-relay.brevo.com` | SMTP server hostname |
| `BREVO_SMTP_PORT` | `587` | SMTP port (TLS) |
| `BREVO_SMTP_USER` | `None` | SMTP login username |
| `BREVO_SMTP_PASSWORD` | `None` | SMTP login password |
| `EMAIL_FROM_NAME` | `Learning Platform` | Display name in From header |
| `EMAIL_FROM_EMAIL` | `noreply@learningplatform.com` | From email address |
| `EMAIL_TEMPLATE_DIR` | `app/templates` | Template file directory |

When `BREVO_SMTP_PASSWORD` is `None`, all send methods return `False` and log a warning — the application continues without sending emails.

---

## Interaction with Other Systems

- **AuthService** — can call `send_email()` after user registration
- **BackgroundTaskManager** — email sending can be wrapped in `execute_with_retry()` for resilient delivery
- **Templates** — Jinja2 HTML files in `app/templates/`

---

## Error Handling Strategy

| Error | Handling |
|---|---|
| Missing SMTP password | Methods return `False` immediately, log warning |
| Template file not found | `FileNotFoundError` caught, logged, returns `False` |
| Template render error | Caught, logged, returns `False` |
| `SMTPAuthenticationError` | Caught specifically, logged with server details |
| Network / SMTP errors | `SMTPException`, `socket.timeout`, `OSError` all caught |

---

## Production Considerations

- **Rate limits** — Brevo free tier has daily sending limits; monitor via their dashboard
- **SPF / DKIM / DMARC** — configure DNS records for your sending domain to avoid spam classification
- **Bounce handling** — configure Brevo webhooks to monitor bounces and complaints
- **Bulk sends** — use `send_bulk_emails()` but be mindful of rate limits; consider queuing with a background task
- **Templates** — keep templates simple HTML for maximum email client compatibility

---

## Example Flow

1. User registers via `POST /lms_be/v1/auth/register`
2. `UserService.create_user()` creates the user in PostgreSQL
3. (Optional) Service calls `EmailService.send_email()`:
   ```python
   EmailService.send_email(
       to_email="newuser@example.com",
       subject="Welcome!",
       template_path="app/templates/welcome.html",
       context={"full_name": "John Doe", "year": 2026},
   )
   ```
4. Template is rendered → MIME message built → SMTP connection opened → email sent
5. Success/failure is logged
