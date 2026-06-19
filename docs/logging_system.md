# Structured Logging System

## Purpose

The logging system provides **structured, machine-parseable logs** (JSON) for production environments and **human-readable console output** for development.  It is built on `structlog` backed by Python's `logging` stdlib for file rotation and transport.

---

## Architecture Overview

```
Application Code
    └── structlog.get_logger(__name__)
            └── Processor Chain (add level, name, timestamp, exc_info)
                    └── Renderer (JSONRenderer or ConsoleRenderer)
                            ├── StreamHandler → Console (stderr)
                            └── RotatingFileHandler → logs/app.log
```

All configuration lives in **`app/core/logging.py`** — it runs once at import time via a `_CONFIGURED` guard.

---

## Implementation Details

### Setup Guard

```python
_CONFIGURED = False

def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True
    # ... configuration ...
```

This prevents duplicate handlers when the module is re-imported (common during testing or reload).

### Processor Chain

| Processor | Purpose |
|---|---|
| `add_log_level` | Adds `"level": "info"` to JSON output |
| `add_logger_name` | Adds `"logger": "app.services.course_service"` |
| `TimeStamper(fmt="iso")` | ISO 8601 timestamps |
| `StackInfoRenderer` | Includes stack trace info when requested |
| `format_exc_info` | Formats exception tracebacks into the log event |
| `JSONRenderer` / `ConsoleRenderer` | Final output format (env-dependent) |

### Request Logging Middleware

`app/middleware/RequestLoggingMiddleware.py` logs every request/response cycle:

```json
{"event": "request_started", "method": "GET", "url": "http://localhost:8000/doit/v1/courses/", "level": "info"}
{"event": "request_finished", "method": "GET", "status_code": 200, "process_time": "0.0042s", "level": "info"}
```

---

## Configuration Variables

| Variable | Default | Description |
|---|---|---|
| `LOG_DIR` | `logs` | Directory for log files |
| `LOG_LEVEL` | `INFO` | Minimum severity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `LOG_JSON` | `true` | JSON output (production) or console format (dev) |
| `LOG_MAX_BYTES` | `5000000` | Max log file size before rotation (~5 MB) |
| `LOG_BACKUP_COUNT` | `5` | Number of rotated log files to keep |
| `ENABLE_FILE_LOGGING` | `true` | Enable/disable file handler |
| `ENABLE_REQUEST_LOGGING` | `true` | Enable/disable console (stderr) handler |

---

## Interaction with Other Systems

- **Middleware** — `RequestLoggingMiddleware` automatically logs all HTTP request/response pairs
- **Services** — every service class creates a logger via `structlog.get_logger(__name__)`
- **Exception handlers** — `app/core/exceptions.py` logs warnings for app exceptions and errors for unhandled exceptions
- **Redis** — cache hits/misses and failures are logged
- **Email / S3** — success and failure events are logged

---

## Error Handling Strategy

- **Application exceptions** → logged at WARNING level with `path`, `status_code`, and `detail`
- **Unhandled exceptions** → logged at ERROR level with `exc_info=True` for full traceback
- **Handler errors** → if the log file is inaccessible, Python's logging falls back to stderr

---

## Production Considerations

- Set `LOG_JSON=true` for JSON output that works with log aggregators (ELK, Datadog, CloudWatch)
- Set `LOG_LEVEL=WARNING` or `ERROR` in production to reduce log volume
- Set `ENABLE_REQUEST_LOGGING=false` if using an external reverse proxy (Nginx) for access logs
- **Log rotation** is built-in via `RotatingFileHandler` — logs are rotated at ~5 MB with 5 backups
- For containerised deployments, consider setting `ENABLE_FILE_LOGGING=false` and relying on stdout/stderr

---

## Example Flow

1. Client sends `POST /doit/v1/auth/login`
2. **Middleware** logs: `request_started (POST /doit/v1/auth/login)`
3. **AuthService** logs: `login_attempt (username=user@example.com)`
4. **AuthService** logs: `login_success (user_id=42)` or `login_failed`
5. **Middleware** logs: `request_finished (200, 0.0123s)`

All events include ISO timestamp, log level, and logger name for full traceability.
