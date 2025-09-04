class RateLimitError(Exception):
    """Base error for RateLimiter component."""

class InvalidScopeError(RateLimitError):
    """Raised when an unsupported scope key is requested."""

class NoMatchingPolicyError(RateLimitError):
    """Raised when no policy matches a request and default handling is disabled."""