"""SQS implementation of QueuePort."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import boto3


class SqsQueue:
    def __init__(self, queue_url: str, region: str, client: Any = None) -> None:
        self._url = queue_url
        self._client = client if client is not None else boto3.client("sqs", region_name=region)

    async def enqueue(self, msg: dict[str, Any]) -> None:
        await asyncio.to_thread(
            self._client.send_message,
            QueueUrl=self._url,
            MessageBody=json.dumps(msg, separators=(",", ":")),
        )

    async def dequeue(self, max_messages: int = 1, wait_seconds: int = 0) -> list[dict[str, Any]]:
        response = await asyncio.to_thread(
            self._client.receive_message,
            QueueUrl=self._url,
            MaxNumberOfMessages=min(max_messages, 10),  # SQS hard cap
            WaitTimeSeconds=min(wait_seconds, 20),  # SQS long-poll cap
        )
        messages = response.get("Messages", [])
        for message in messages:
            # At-least-once delivery: delete after reading, matching the local
            # queue's take-once semantics.
            await asyncio.to_thread(
                self._client.delete_message,
                QueueUrl=self._url,
                ReceiptHandle=message["ReceiptHandle"],
            )
        return [json.loads(m["Body"]) for m in messages]
