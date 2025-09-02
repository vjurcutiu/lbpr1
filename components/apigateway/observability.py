from __future__ import annotations
import time, uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger("apigateway")

class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        start = time.perf_counter()
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        tenant_id = request.headers.get("x-tenant-id")  # optional mirror
        # In real use, we would fetch/attach trace_id from OTel context
        trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())

        request.state.request_id = request_id
        request.state.tenant_id = tenant_id
        request.state.trace_id = trace_id

        logger.info(
            "request.start",
            extra={"request_id": request_id, "trace_id": trace_id, "path": request.url.path, "method": request.method}
        )
        try:
            response: Response = await call_next(request)
            duration_ms = int((time.perf_counter() - start) * 1000)
            response.headers["x-request-id"] = request_id
            response.headers["x-trace-id"] = trace_id
            logger.info(
                "request.end",
                extra={"request_id": request_id, "trace_id": trace_id, "status": response.status_code, "duration_ms": duration_ms}
            )
            return response
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.exception(
                "request.exception",
                extra={"request_id": request_id, "trace_id": trace_id, "duration_ms": duration_ms}
            )
            raise
