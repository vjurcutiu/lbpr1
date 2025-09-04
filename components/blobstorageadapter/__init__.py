from __future__ import annotations
from .contracts import *
from .errors import *
from .ports import BlobStoragePort
from .adapters.local_fs import LocalFSBlobAdapter
try:
    from .adapters.s3 import S3BlobAdapter
except Exception:  # pragma: no cover
    S3BlobAdapter = None  # type: ignore

from .config import BlobSettings

def make_adapter_from_env():
    cfg = BlobSettings()
    if cfg.BLOB_ADAPTER.lower() == "localfs":
        return LocalFSBlobAdapter(cfg.BLOB_LOCAL_ROOT), "localfs"
    elif cfg.BLOB_ADAPTER.lower() == "s3":
        if S3BlobAdapter is None:
            raise RuntimeError("S3 adapter requested but boto3 not available")
        if not cfg.S3_BUCKET_DEFAULT:
            raise RuntimeError("S3_BUCKET_DEFAULT is required for S3 adapter")
        return S3BlobAdapter(
            bucket_default=cfg.S3_BUCKET_DEFAULT,
            region=cfg.AWS_REGION,
            endpoint_url=cfg.S3_ENDPOINT_URL,
            force_path_style=cfg.S3_FORCE_PATH_STYLE
        ), "s3"
    else:
        raise RuntimeError(f"Unknown BLOB_ADAPTER: {cfg.BLOB_ADAPTER}")
