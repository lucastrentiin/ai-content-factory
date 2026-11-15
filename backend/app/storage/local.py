from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

from app.storage.base import Storage, safe_key


class LocalStorage(Storage):
    backend = "local"

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / safe_key(key)).resolve()
        if self.root not in p.parents and p != self.root:
            raise ValueError("chave de storage inválida")
        return p

    def put_file(self, local_path: Path, key: str, mime: str = "application/octet-stream") -> None:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if Path(local_path).resolve() != dest:
            shutil.copyfile(local_path, dest)

    def put_bytes(self, data: bytes, key: str, mime: str = "application/octet-stream") -> None:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def download(self, key: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self._path(key), dest)
        return dest

    def read_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()

    def size(self, key: str) -> int:
        return self._path(key).stat().st_size

    def iter_chunks(self, key: str, start: int = 0, end: int | None = None, chunk: int = 1 << 20) -> Iterator[bytes]:
        p = self._path(key)
        total = p.stat().st_size
        end = total - 1 if end is None else min(end, total - 1)
        with p.open("rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                data = f.read(min(chunk, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    def local_path(self, key: str) -> Path:
        return self._path(key)
