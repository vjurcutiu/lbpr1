from __future__ import annotations
import os

APP_NAME = "lbp3-rs-apigateway"
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
REQUEST_BODY_MAX_BYTES = int(os.getenv("APIGW_BODY_MAX_BYTES", "10485760"))  # 10 MiB

# Rate limits (example defaults)
LIMIT_SEARCH_PER_MIN = int(os.getenv("APIGW_LIMIT_SEARCH_PER_MIN", "120"))
LIMIT_CHAT_PER_MIN = int(os.getenv("APIGW_LIMIT_CHAT_PER_MIN", "60"))
LIMIT_INGEST_PER_MIN = int(os.getenv("APIGW_LIMIT_INGEST_PER_MIN", "30"))
