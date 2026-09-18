"""S3 implementation of BlobStorePort."""

from __future__ import annotations

import asyncio

import boto3
from botocore.exceptions import ClientError


class S3BlobStore:
    def __init__(self, bucket: str, region: str, client: object | None = None) -> None:
        self._bucket = bucket
        self._client = client if client is not None else boto3.client("s3", region_name=region)

    async def put_object(self, key: str, data: bytes, content_type: str) -> str:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key

    async def get_object(self, key: str) -> bytes:
        try:
            response = await asyncio.to_thread(
                self._client.get_object, Bucket=self._bucket, Key=key
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                # Match FsBlobStore, so callers handle one exception type.
                raise KeyError(key) from exc
            raise
        return bytes(response["Body"].read())

    async def presign_get(self, key: str, ttl_seconds: int = 900) -> str:
        return str(
            await asyncio.to_thread(
                self._client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=ttl_seconds,
            )
        )

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(self._client.head_object, Bucket=self._bucket, Key=key)
        except ClientError:
            return False
        return True
