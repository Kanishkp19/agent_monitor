"""BlobStorePort contract -- runs against the filesystem and S3.

The blob store is the only home for raw prompts. If these two disagree about
what a key means, a secret ends up somewhere it was not meant to be.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.contract


async def test_put_and_get_round_trip(blobstore: Any) -> None:
    await blobstore.put_object(
        "raw/task_9c21/prompt.json", b'{"prompt":"hello"}', "application/json"
    )
    assert await blobstore.get_object("raw/task_9c21/prompt.json") == b'{"prompt":"hello"}'


async def test_get_missing_raises_key_error(blobstore: Any) -> None:
    """One exception type across both stores, so callers need one branch."""
    with pytest.raises(KeyError):
        await blobstore.get_object("raw/does-not-exist/prompt.json")


async def test_overwrite(blobstore: Any) -> None:
    await blobstore.put_object("raw/t/p.json", b"first", "application/json")
    await blobstore.put_object("raw/t/p.json", b"second", "application/json")
    assert await blobstore.get_object("raw/t/p.json") == b"second"


async def test_nested_keys(blobstore: Any) -> None:
    """S3 keys are flat strings with slashes; the local store must not care
    that the directory did not exist.
    """
    key = "exports/2026/09/18/sessions.parquet"
    await blobstore.put_object(key, b"PAR1", "application/octet-stream")
    assert await blobstore.get_object(key) == b"PAR1"


async def test_binary_payloads_are_not_mangled(blobstore: Any) -> None:
    payload = bytes(range(256))
    await blobstore.put_object("raw/t/blob.bin", payload, "application/octet-stream")
    assert await blobstore.get_object("raw/t/blob.bin") == payload


async def test_exists(blobstore: Any) -> None:
    assert await blobstore.exists("raw/t/p.json") is False
    await blobstore.put_object("raw/t/p.json", b"x", "text/plain")
    assert await blobstore.exists("raw/t/p.json") is True


async def test_presign_returns_a_locator(blobstore: Any) -> None:
    await blobstore.put_object("raw/t/p.json", b"x", "application/json")
    url = await blobstore.presign_get("raw/t/p.json", ttl_seconds=60)
    assert isinstance(url, str) and url
