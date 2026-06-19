import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)
CORRELATION_HEADER = "X-Correlation-ID"

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = request.headers.get(CORRELATION_HEADER) or str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        # Bind the correlation ID so all subsequent logs in this request include it
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        start_time = time.time()
        logger.info(
            "request_started",
            method=request.method,
            path=request.url.path,
            client_host=request.client.host if request.client else None
        )

        try:
            response = await call_next(request)
            process_time = time.time() - start_time

            response.headers[CORRELATION_HEADER] = correlation_id

            logger.info(
                "request_finished",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration=round(process_time, 4)
            )
            return response
        finally:
            # Always clear context vars to prevent leaking to other requests in async workers
            structlog.contextvars.clear_contextvars()
