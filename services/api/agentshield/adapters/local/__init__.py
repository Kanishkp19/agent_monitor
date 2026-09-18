"""Local adapter set: SQLite, filesystem, in-process bus, Ollama/Mock.

Imported by `container.py` and by the contract tests. Nothing else in the
backend may import from this package -- `tests/test_architecture.py` asserts it.

`aiosqlite` and `httpx` appear here and nowhere else in the codebase.
"""

from agentshield.adapters.local.asyncio_queue import AsyncioQueue
from agentshield.adapters.local.dotenv_secrets import DotenvSecrets
from agentshield.adapters.local.fs_blobstore import FsBlobStore
from agentshield.adapters.local.memory_eventbus import MemoryBus
from agentshield.adapters.local.mock_llm import MockLLMAdapter
from agentshield.adapters.local.ollama_llm import OllamaAdapter
from agentshield.adapters.local.sqlite_docstore import SqliteDocStore
from agentshield.adapters.local.stdout_metrics import StdoutMetrics

__all__ = [
    "AsyncioQueue",
    "DotenvSecrets",
    "FsBlobStore",
    "MemoryBus",
    "MockLLMAdapter",
    "OllamaAdapter",
    "SqliteDocStore",
    "StdoutMetrics",
]
