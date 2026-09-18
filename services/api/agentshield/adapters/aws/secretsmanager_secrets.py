"""Secrets Manager implementation of SecretsPort.

Values are cached after first read. Secrets Manager charges per API call and
these are read on every ingest request; a secret rotation requires a restart,
which is the correct trade for a control plane that must not add latency to a
governance decision.
"""

from __future__ import annotations

import asyncio

import boto3
from botocore.exceptions import ClientError


class SecretsManagerSecrets:
    def __init__(
        self, region: str, prefix: str = "agentshield/", client: object | None = None
    ) -> None:
        self._prefix = prefix
        self._client = (
            client if client is not None else boto3.client("secretsmanager", region_name=region)
        )
        self._cache: dict[str, str] = {}

    async def get(self, name: str) -> str:
        if name in self._cache:
            return self._cache[name]
        try:
            response = await asyncio.to_thread(
                self._client.get_secret_value, SecretId=f"{self._prefix}{name}"
            )
        except ClientError as exc:
            raise KeyError(f"secret {name!r} is not available") from exc
        value = str(response["SecretString"])
        self._cache[name] = value
        return value
