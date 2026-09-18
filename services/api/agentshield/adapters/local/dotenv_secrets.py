"""Environment-variable implementation of SecretsPort.

Local stand-in for Secrets Manager. Reads the process environment, which
`config.py` has already populated from `.env`.
"""

from __future__ import annotations

import os


class DotenvSecrets:
    def __init__(self, prefix: str = "") -> None:
        self._prefix = prefix

    async def get(self, name: str) -> str:
        key = f"{self._prefix}{name}"
        value = os.environ.get(key)
        if value is None:
            raise KeyError(f"secret {key!r} is not set")
        return value
