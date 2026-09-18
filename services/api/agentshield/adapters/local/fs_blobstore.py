"""Filesystem implementation of BlobStorePort.

Mirrors S3 key semantics: keys are `/`-separated paths, and a key is not a
filesystem path the caller controls -- it is normalised and confined to the
configured root. `raw/{task_id}/prompt.json` must never be able to escape into
the repository.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path, PurePosixPath

_META_SUFFIX = ".meta.json"


class FsBlobStore:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    async def put_object(self, key: str, data: bytes, content_type: str) -> str:
        path = self._resolve(key)
        await asyncio.to_thread(self._write, path, data, content_type)
        return key

    async def get_object(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.is_file():
            raise KeyError(key)
        return await asyncio.to_thread(path.read_bytes)

    async def presign_get(self, key: str, ttl_seconds: int = 900) -> str:
        """No signing locally -- there is nothing to sign against.

        Returns a `file://` URL so callers can be written once. The TTL is
        accepted and ignored; the contract test asserts only that a resolvable
        locator comes back.
        """
        return self._resolve(key).as_uri()

    async def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def _write(self, path: Path, data: bytes, content_type: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        # S3 carries content type as object metadata; keep a sidecar so the
        # local adapter can answer the same questions.
        path.with_suffix(path.suffix + _META_SUFFIX).write_text(
            json.dumps({"content_type": content_type}), encoding="utf-8"
        )

    def _resolve(self, key: str) -> Path:
        """Map an S3-style key to a path inside the root, or refuse."""
        pure = PurePosixPath(key)
        if pure.is_absolute() or any(part == ".." for part in pure.parts):
            raise ValueError(f"unsafe blob key: {key!r}")
        candidate = (self._root / Path(*pure.parts)).resolve()
        if not candidate.is_relative_to(self._root):
            raise ValueError(f"blob key escapes the store root: {key!r}")
        return candidate
