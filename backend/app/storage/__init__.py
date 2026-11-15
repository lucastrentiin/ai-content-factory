from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.storage.base import Storage


@lru_cache
def get_storage() -> Storage:
    if settings.storage_backend == "s3":
        from app.storage.s3 import S3Storage

        return S3Storage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            public_endpoint_url=settings.s3_public_endpoint_url,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
        )
    from app.storage.local import LocalStorage

    return LocalStorage(settings.storage_local_path)
