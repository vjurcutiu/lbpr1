from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field, PositiveInt, field_validator
import re

Algorithm = Literal["token_bucket", "leaky_bucket"]
Scope = Literal["ip", "user", "tenant", "global", "custom"]

class Policy(BaseModel):
    name: str = Field(..., description="Unique policy name")
    algorithm: Algorithm = Field("token_bucket")
    rate: PositiveInt = Field(..., description="Tokens per period")
    period: PositiveInt = Field(..., description="Period length in seconds")
    burst: PositiveInt = Field(..., description="Max tokens in bucket")
    scope: Scope = Field("ip")
    path_pattern: str = Field(r".*", description="Regex to match request path")
    methods: Optional[List[str]] = Field(None, description="List of HTTP methods; None means all")
    cost: PositiveInt = Field(1, description="Default cost per request")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("methods")
    @classmethod
    def normalize_methods(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        return [m.upper() for m in v]

    def matches(self, method: str, path: str) -> bool:
        if self.methods and method.upper() not in self.methods:
            return False
        return re.search(self.path_pattern, path) is not None


class ConsumeRequest(BaseModel):
    key: str
    policy: Policy
    cost: PositiveInt = 1


class ConsumeResult(BaseModel):
    allowed: bool
    remaining: float
    retry_after: Optional[float] = None
    policy: str
    key: str


class QuotaSnapshot(BaseModel):
    key: str
    tokens: Optional[float] = None
    last_refill_ts: Optional[float] = None
    level: Optional[float] = None
    algorithm: Algorithm