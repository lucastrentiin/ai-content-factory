from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.storage.base import Storage, safe_key


class S3Storage(Storage):
    backend = "s3"

    def __init__(self, *, bucket: str, endpoint_url: str | None, public_endpoint_url: str | None,
                 access_key: str | None, secret_key: str | None, region: str):
        self.bucket = bucket
        cfg = Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 5, "mode": "standard"})
        common = dict(aws_access_key_id=access_key, aws_secret_access_key=secret_key, region_name=region, config=cfg)
        self.client = boto3.client("s3", endpoint_url=endpoint_url, **common)
        # cliente separado para gerar URLs com o host público (ex.: https://files.meudominio.com)
        self.public_client = boto3.client("s3", endpoint_url=public_endpoint_url or endpoint_url, **common)
        self._bucket_checked = False

    def _ensure_bucket(self) -> None:
        if self._bucket_checked:
            return
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)
        self._bucket_checked = True

    def put_file(self, local_path: Path, key: str, mime: str = "application/octet-stream") -> None:
        self._ensure_bucket()
        self.client.upload_file(str(local_path), self.bucket, safe_key(key), ExtraArgs={"ContentType": mime})

    def put_bytes(self, data: bytes, key: str, mime: str = "application/octet-stream") -> None:
        self._ensure_bucket()
        self.client.put_object(Bucket=self.bucket, Key=safe_key(key), Body=data, ContentType=mime)

    def download(self, key: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, safe_key(key), str(dest))
        return dest

    def read_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=safe_key(key))["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=safe_key(key))
            return True
        except ClientError:
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=safe_key(key))

    def size(self, key: str) -> int:
        return int(self.client.head_object(Bucket=self.bucket, Key=safe_key(key))["ContentLength"])

    def iter_chunks(self, key: str, start: int = 0, end: int | None = None, chunk: int = 1 << 20) -> Iterator[bytes]:
        rng = f"bytes={start}-{'' if end is None else end}"
        body = self.client.get_object(Bucket=self.bucket, Key=safe_key(key), Range=rng)["Body"]
        yield from body.iter_chunks(chunk)

    def public_url(self, key: str, expires_s: int = 3600) -> str | None:
        return self.public_client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": safe_key(key)}, ExpiresIn=expires_s
        )

    def healthcheck(self) -> bool:
        try:
            self._ensure_bucket()
            return True
        except Exception:
            return False
