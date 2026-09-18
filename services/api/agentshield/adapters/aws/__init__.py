"""AWS adapter set: Bedrock, DynamoDB, S3, EventBridge, CloudWatch, SQS.

Imported by `container.py` and by the contract tests (under moto). Nothing else
in the backend may import from this package -- `tests/test_architecture.py`
asserts it, and `pyproject.toml` bans the `boto3` import outright everywhere
else.

These were written in Phase 0, alongside the local set, rather than deferred to
Phase 9. An adapter written months after its port drifts from it; an adapter
written the same afternoon does not, and the shared contract suite proves it.
"""

from agentshield.adapters.aws.bedrock_llm import BedrockAdapter
from agentshield.adapters.aws.cloudwatch_metrics import CloudWatchEmfMetrics
from agentshield.adapters.aws.dynamo_docstore import DynamoDocStore
from agentshield.adapters.aws.eventbridge_bus import EventBridgeBus
from agentshield.adapters.aws.s3_blobstore import S3BlobStore
from agentshield.adapters.aws.secretsmanager_secrets import SecretsManagerSecrets
from agentshield.adapters.aws.sqs_queue import SqsQueue

__all__ = [
    "BedrockAdapter",
    "CloudWatchEmfMetrics",
    "DynamoDocStore",
    "EventBridgeBus",
    "S3BlobStore",
    "SecretsManagerSecrets",
    "SqsQueue",
]
