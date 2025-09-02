from __future__ import annotations
from typing import Dict, Optional
from pydantic import BaseModel

class ApiGatewayError(Exception):
    type: str = "INTERNAL"
    code: str = "internal_error"
    message: str = "Internal server error"
    details: Optional[Dict] = None
    status_code: int = 500

    def to_payload(self):
        return {
            "type": self.type,
            "code": self.code,
            "message": self.message,
            "details": self.details or {},
        }

class AuthError(ApiGatewayError):
    type = "AUTH_ERROR"
    code = "auth_failed"
    message = "Authentication failed"
    status_code = 401

class ForbiddenError(ApiGatewayError):
    type = "AUTH_ERROR"
    code = "forbidden"
    message = "Not enough privileges"
    status_code = 403

class RateLimitError(ApiGatewayError):
    type = "RATE_LIMIT"
    code = "rate_limited"
    message = "Rate limit exceeded"
    status_code = 429

class ValidationError(ApiGatewayError):
    type = "VALIDATION"
    code = "validation_error"
    message = "Validation error"
    status_code = 422

class NotFoundError(ApiGatewayError):
    type = "NOT_FOUND"
    code = "not_found"
    message = "Resource not found"
    status_code = 404

class UpstreamError(ApiGatewayError):
    type = "UPSTREAM"
    code = "upstream_error"
    message = "Upstream dependency failed"
    status_code = 502
