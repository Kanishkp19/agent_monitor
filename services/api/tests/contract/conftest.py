"""Fixtures that yield each port twice: once local, once AWS.

Every test in this package runs against both adapter sets. That is the whole
mechanism behind the thirty-minute AWS migration -- a change that breaks parity
fails here, eight days before a deploy would have found it.

`moto` stands in for AWS, so the suite needs no account and no credentials.
A test that *skips* the `aws` parameter is worse than a failing one, because it
reports green. `tests/contract/test_no_skips.py` asserts that never happens.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

import boto3
import pytest
from moto import mock_aws

from agentshield.adapters.aws import DynamoDocStore, EventBridgeBus, S3BlobStore, SqsQueue
from agentshield.adapters.local import (
    AsyncioQueue,
    FsBlobStore,
    MemoryBus,
    SqliteDocStore,
)

ADAPTER_SETS = ["local", "aws"]
REGION = "ap-south-1"
TABLE = "agentshield-test"
BUCKET = "agentshield-test-bucket"
BUS = "agentshield-test-bus"


@pytest.fixture(autouse=True)
def _fake_aws_credentials() -> Iterator[None]:
    """moto must never reach a real account, even by accident."""
    saved = {k: os.environ.get(k) for k in _CRED_KEYS}
    os.environ.update(
        {
            "AWS_ACCESS_KEY_ID": "testing",
            "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_SECURITY_TOKEN": "testing",
            "AWS_SESSION_TOKEN": "testing",
            "AWS_DEFAULT_REGION": REGION,
        }
    )
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


_CRED_KEYS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SECURITY_TOKEN",
    "AWS_SESSION_TOKEN",
    "AWS_DEFAULT_REGION",
)


@pytest.fixture(params=ADAPTER_SETS)
def adapter_set(request: pytest.FixtureRequest) -> str:
    return str(request.param)


# ──────────────────────────────────────────────────────────────────────
# No-skip guard
# ──────────────────────────────────────────────────────────────────────

_skipped: list[str] = []


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.skipped and "tests/contract" in report.nodeid.replace("\\", "/"):
        _skipped.append(report.nodeid)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """A skipped contract test is worse than a failing one.

    It reports green while proving nothing, and the thing it was not proving
    is that both adapter sets behave identically. The docs put it plainly: a
    skip here is the AWS migration failing eight days early.
    """
    if _skipped:
        session.exitstatus = 1
        print(
            "\nCONTRACT SKIP: these must run against both adapter sets:\n  " + "\n  ".join(_skipped)
        )


# ──────────────────────────────────────────────────────────────────────
# DocStore
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
async def docstore(adapter_set: str) -> AsyncIterator[Any]:
    if adapter_set == "local":
        store = SqliteDocStore(":memory:")
        await store.connect()
        yield store
        await store.close()
    else:
        with mock_aws():
            _create_table()
            yield DynamoDocStore(TABLE, REGION)


def _create_table() -> None:
    """The table shape from `docs/05-BACKEND-SCHEMA.md` section 3.1.

    Kept in step with `infra/aws/template.yaml` -- the contract tests are the
    only place the schema is exercised before a real deploy.
    """
    client = boto3.client("dynamodb", region_name=REGION)
    client.create_table(
        TableName=TABLE,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": n, "AttributeType": "S"}
            for n in ("pk", "sk", "gsi1pk", "gsi1sk", "gsi2pk", "gsi2sk")
        ],
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": index,
                "KeySchema": [
                    {"AttributeName": f"{index}pk", "KeyType": "HASH"},
                    {"AttributeName": f"{index}sk", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
            for index in ("gsi1", "gsi2")
        ],
    )


# ──────────────────────────────────────────────────────────────────────
# BlobStore
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
async def blobstore(adapter_set: str, tmp_path: Any) -> AsyncIterator[Any]:
    if adapter_set == "local":
        yield FsBlobStore(tmp_path / "blobs")
    else:
        with mock_aws():
            boto3.client("s3", region_name=REGION).create_bucket(
                Bucket=BUCKET,
                CreateBucketConfiguration={"LocationConstraint": REGION},
            )
            yield S3BlobStore(BUCKET, REGION)


# ──────────────────────────────────────────────────────────────────────
# EventBus
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
async def eventbus(adapter_set: str) -> AsyncIterator[Any]:
    if adapter_set == "local":
        store = SqliteDocStore(":memory:")
        await store.connect()
        yield MemoryBus(outbox=store)
        await store.close()
    else:
        with mock_aws():
            boto3.client("events", region_name=REGION).create_event_bus(Name=BUS)
            yield EventBridgeBus(BUS, REGION)


# ──────────────────────────────────────────────────────────────────────
# Queue
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
async def queue(adapter_set: str) -> AsyncIterator[Any]:
    if adapter_set == "local":
        yield AsyncioQueue()
    else:
        with mock_aws():
            client = boto3.client("sqs", region_name=REGION)
            url = client.create_queue(QueueName="agentshield-test")["QueueUrl"]
            yield SqsQueue(url, REGION)
