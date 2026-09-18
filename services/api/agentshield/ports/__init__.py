"""The eight ports -- AgentShield's entire contract with the outside world.

Domain code imports from here and **only** from here. It never imports
`boto3`, `sqlite3` or `httpx`; if it needs one, it needs a port instead.
`container.py` is the only file allowed to import from `adapters/`.

    LLMPort . DocStorePort . BlobStorePort . EventBusPort
    MetricsPort . QueuePort . SecretsPort . ClockPort

Each has exactly two implementations (except `ClockPort`, deliberately one)
and a shared contract test suite in `tests/contract/` that both must pass.
"""

from agentshield.ports.blobstore import BlobStorePort
from agentshield.ports.clock import ClockPort
from agentshield.ports.docstore import DocItem, DocStorePort, IndexName, QueryPage
from agentshield.ports.eventbus import EventBusPort, EventHandler
from agentshield.ports.llm import LLMPort, LLMResult, LLMToolCall, LLMUsage, StopReason
from agentshield.ports.metrics import MetricsPort
from agentshield.ports.queue import QueuePort
from agentshield.ports.secrets import SecretsPort

__all__ = [
    "BlobStorePort",
    "ClockPort",
    "DocItem",
    "DocStorePort",
    "EventBusPort",
    "EventHandler",
    "IndexName",
    "LLMPort",
    "LLMResult",
    "LLMToolCall",
    "LLMUsage",
    "MetricsPort",
    "QueryPage",
    "QueuePort",
    "SecretsPort",
    "StopReason",
]
