"""Abstração de armazenamento de arquivos (local ou compatível com S3/MinIO)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path


class Storage(ABC):
    backend: str

    @abstractmethod
    def put_file(self, local_path: Path, key: str, mime: str = "application/octet-stream") -> None: ...

    @abstractmethod
    def put_bytes(self, data: bytes, key: str, mime: str = "application/octet-stream") -> None: ...

    @abstractmethod
    def download(self, key: str, dest: Path) -> Path: ...

    @abstractmethod
    def read_bytes(self, key: str) -> bytes: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def iter_chunks(self, key: str, start: int = 0, end: int | None = None, chunk: int = 1 << 20) -> Iterator[bytes]: ...

    @abstractmethod
    def size(self, key: str) -> int: ...

    def public_url(self, key: str, expires_s: int = 3600) -> str | None:
        """URL acessível externamente (necessária p/ ex. na API do Instagram). None se indisponível."""
        return None

    def healthcheck(self) -> bool:
        return True


def safe_key(key: str) -> str:
    key = key.replace("\\", "/").lstrip("/")
    parts = [p for p in key.split("/") if p not in ("", ".", "..")]
    return "/".join(parts)
