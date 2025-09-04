
from __future__ import annotations
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional

class BlobSettings(BaseSettings):
    BLOB_ADAPTER: str = Field(default="localfs")  # "localfs" | "s3"
    # Local FS
    BLOB_LOCAL_ROOT: str = Field(default="./var/blobdata")
    # S3
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: Optional[str] = None
    S3_BUCKET_DEFAULT: Optional[str] = None
    S3_ENDPOINT_URL: Optional[str] = None
    S3_FORCE_PATH_STYLE: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = False

### 6) Local FS Adapter
