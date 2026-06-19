import logging
import os
from logging.handlers import RotatingFileHandler
import structlog
from app.core.config import settings

_CONFIGURED = False

def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True
    os.makedirs(settings.LOG_DIR, exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    # Take full control (prevents weird duplication issues)
    root_logger.handlers.clear()
    root_logger.propagate = False
    # Structlog processors
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer = structlog.processors.JSONRenderer() if settings.LOG_JSON else structlog.dev.ConsoleRenderer()
    formatter = structlog.stdlib.ProcessorFormatter( processor=renderer, foreign_pre_chain=processors,)

    structlog.configure(
        processors=processors + [renderer],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    # Console logging
    if settings.ENABLE_CONSOLE_LOGGING:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(root_logger.level)
        root_logger.addHandler(console_handler)

    # File logging (optional)
    if settings.ENABLE_FILE_LOGGING:
        log_path = os.path.join(settings.LOG_DIR, "app.log")
        file_handler = RotatingFileHandler(log_path, maxBytes=settings.LOG_MAX_BYTES,backupCount=settings.LOG_BACKUP_COUNT,)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(root_logger.level)
        root_logger.addHandler(file_handler)

    # Fallback
    if not root_logger.handlers:
        root_logger.addHandler(logging.NullHandler())

setup_logging()
logger = structlog.get_logger()

# import logging
# import os
# from logging.handlers import RotatingFileHandler

# import structlog

# from app.core.config import settings

# _CONFIGURED = False


# def setup_logging() -> None:
#     global _CONFIGURED
#     if _CONFIGURED:
#         return
#     _CONFIGURED = True

#     os.makedirs(settings.LOG_DIR, exist_ok=True)

#     # ── Stdlib root logger ────────────────────────────────────────────
#     root_logger = logging.getLogger()
#     root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

#     if root_logger.handlers:
#         return
#     formatter = logging.Formatter("%(message)s")

#     # ── Structlog processor chain ─────────────────────────────────────
#     # directing the structlog Logs
#     processors = [
#         structlog.stdlib.add_log_level,
#         structlog.stdlib.add_logger_name,
#         structlog.processors.TimeStamper(fmt="iso"),
#         structlog.processors.StackInfoRenderer(),
#         structlog.processors.format_exc_info,
#     ]

#     # Final renderer: JSON for production, console for development
#     if settings.LOG_JSON:
#         processors.append(structlog.processors.JSONRenderer())
#     else:
#         processors.append(structlog.dev.ConsoleRenderer())

#     structlog.configure(
#         processors=processors,
#         context_class=dict,
#         logger_factory=structlog.stdlib.LoggerFactory(),
#         wrapper_class=structlog.stdlib.BoundLogger,
#         cache_logger_on_first_use=True,
#     )
#     has_handlers:bool = False
#     #handlers are configued and added
#     if settings.ENABLE_FILE_LOGGING:
#         log_path = os.path.join(settings.LOG_DIR, "app.log")
#         file_handler = RotatingFileHandler(
#             log_path,
#             maxBytes=settings.LOG_MAX_BYTES,
#             backupCount=settings.LOG_BACKUP_COUNT,
#         )
#         file_handler.setFormatter(formatter)
#         root_logger.addHandler(file_handler)
#         has_handlers = True

#     if settings.ENABLE_CONSOLE_LOGGING:
#         console_handler = logging.StreamHandler()
#         console_handler.setFormatter(formatter)
#         root_logger.addHandler(console_handler)
#         has_handlers = True

#     if not has_handlers:
#         root_logger.addHandler(logging.NullHandler())


# # ── Module-level init ────────────────────────
# setup_logging()
# logger = structlog.get_logger()

# """
# Structured logging configuration using structlog + stdlib logging.

# Initialises once at import time.  Outputs are controlled by env settings:
#   - LOG_JSON (bool)  → JSON lines or human-readable console output
#   - ENABLE_FILE_LOGGING  → rotating file handler  (logs/app.log)
#   - ENABLE_REQUEST_LOGGING → console/stderr stream handler
#   - LOG_LEVEL  → root logger severity threshold

# This module is imported as a side-effect in main.py to ensure logging is
# configured before any other module emits log messages::

#     from app.core import logging  # noqa: F401  — initialises structlog
# """

# import logging
# import os
# from logging.handlers import RotatingFileHandler

# import structlog

# from app.core.config import settings

# _CONFIGURED = False


# def setup_logging() -> None:
#     """
#     Configure structlog processors and stdlib log handlers.

#     Guarded by `_CONFIGURED` to prevent duplicate handlers being
#     attached when the module is re-imported (e.g. during testing).
#     """
#     global _CONFIGURED
#     if _CONFIGURED:
#         return
#     _CONFIGURED = True

#     os.makedirs(settings.LOG_DIR, exist_ok=True)

#     # ── Structlog processor chain ─────────────────────────────────────
#     processors = [
#         structlog.stdlib.add_log_level,
#         structlog.stdlib.add_logger_name,
#         structlog.processors.TimeStamper(fmt="iso"),
#         structlog.processors.StackInfoRenderer(),
#         structlog.processors.format_exc_info,
#     ]

#     # Final renderer: JSON for production, console for development
#     if settings.LOG_JSON:
#         processors.append(structlog.processors.JSONRenderer())
#     else:
#         processors.append(structlog.dev.ConsoleRenderer())

#     structlog.configure(
#         processors=processors,
#         context_class=dict,
#         logger_factory=structlog.stdlib.LoggerFactory(),
#         wrapper_class=structlog.stdlib.BoundLogger,
#         cache_logger_on_first_use=True,
#     )

#     # ── Stdlib root logger ────────────────────────────────────────────
#     root_logger = logging.getLogger()
#     root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

#     # Prevent adding handlers multiple times
#     if root_logger.handlers:
#         return

#     formatter = logging.Formatter("%(message)s")

#     if settings.ENABLE_FILE_LOGGING:
#         log_path = os.path.join(settings.LOG_DIR, "app.log")
#         file_handler = RotatingFileHandler(
#             log_path,
#             maxBytes=settings.LOG_MAX_BYTES,
#             backupCount=settings.LOG_BACKUP_COUNT,
#         )
#         file_handler.setFormatter(formatter)
#         root_logger.addHandler(file_handler)

#     if settings.ENABLE_REQUEST_LOGGING:
#         console_handler = logging.StreamHandler()
#         console_handler.setFormatter(formatter)
#         root_logger.addHandler(console_handler)


# # ── Module-level init ─────────────────────────────────────────────────────
# setup_logging()
# logger = structlog.get_logger()
