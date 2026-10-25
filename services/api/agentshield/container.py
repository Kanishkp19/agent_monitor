"""The composition root.

**This is the only file in the backend that branches on the environment.**
Every other module depends on `agentshield.ports` and has no way to learn
whether it is talking to SQLite or DynamoDB, Ollama or Bedrock.

That single constraint is what makes the AWS migration a configuration change
rather than a rewrite, and it is enforced three ways:

  1. `tests/test_architecture.py` -- AST walk, asserts no other module
     imports `agentshield.adapters` or compares `settings.env`.
  2. `pyproject.toml` -- ruff bans importing `boto3` and `aiosqlite` anywhere
     the adapters do not live.
  3. `tests/contract/` -- both adapter sets pass the same suite, so a
     divergence fails CI before it reaches a deploy.

See `docs/DECISIONS-RESOLVED.md` C6 for why `config.py` may *read*
`AGENTSHIELD_ENV` while only this file may *branch* on it.
"""

from __future__ import annotations

from functools import lru_cache

from agentshield.config import Settings
from agentshield.ports import (
    BlobStorePort,
    ClockPort,
    DocStorePort,
    EventBusPort,
    LLMPort,
    MetricsPort,
    QueuePort,
    SecretsPort,
)
from agentshield.sim.clock import SimClock


class Container:
    """Holds one adapter per port, chosen once at startup."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        # ClockPort has a single implementation in both environments.
        self.clock: ClockPort = SimClock(
            seed_ts=settings.sim_start_ts, speed=settings.sim_default_speed
        )

        if settings.env == "aws":
            from agentshield.adapters.aws import (
                BedrockAdapter,
                CloudWatchEmfMetrics,
                DynamoDocStore,
                EventBridgeBus,
                S3BlobStore,
                SecretsManagerSecrets,
                SqsQueue,
            )

            self.docstore: DocStorePort = DynamoDocStore(settings.table, settings.region)
            self.blobs: BlobStorePort = S3BlobStore(settings.bucket, settings.region)
            self.bus: EventBusPort = EventBridgeBus(settings.bus, settings.region)
            self.metrics: MetricsPort = CloudWatchEmfMetrics(settings.cw_namespace)
            self.queue: QueuePort = SqsQueue(settings.sqs_queue_url, settings.region)
            self.secrets: SecretsPort = SecretsManagerSecrets(settings.region)
            self.llm: LLMPort = BedrockAdapter(settings)
        else:
            from agentshield.adapters.local import (
                AsyncioQueue,
                DotenvSecrets,
                FsBlobStore,
                HybridAdapter,
                MemoryBus,
                MockLLMAdapter,
                NebiusAdapter,
                OllamaAdapter,
                SqliteDocStore,
                StdoutMetrics,
            )

            docstore = SqliteDocStore(settings.sqlite_file)
            self.docstore = docstore
            self.blobs = FsBlobStore(settings.blob_path)
            self.bus = MemoryBus(outbox=docstore)
            self.metrics = StdoutMetrics(settings.cw_namespace)
            self.queue = AsyncioQueue()
            self.secrets = DotenvSecrets()
            # `mock` is the default so a fresh clone runs with no model
            # installed and no network. `bedrock` is meaningless locally.
            # `mock` is the default so a fresh clone runs with no model
            # installed and no network. `bedrock` is meaningless locally;
            # `hybrid` is cloud -> ollama -> mock, all free tiers.
            if settings.llm_provider == "hybrid":
                self.llm = HybridAdapter(settings)
            elif settings.llm_provider == "nebius":
                # Live NVIDIA Nemotron via Nebius Token Factory. No mock
                # fallback exists on this path: a failing provider raises
                # `LLMUnavailable` and the caller reports an honest failure.
                self.llm = NebiusAdapter(settings)
            elif settings.llm_provider == "ollama":
                self.llm = OllamaAdapter(settings)
            else:
                self.llm = MockLLMAdapter(seed=settings.sim_seed)

    # ── lifecycle, driven by the FastAPI lifespan ────────────────────

    async def startup(self) -> None:
        opener = getattr(self.docstore, "connect", None)
        if opener is not None:
            await opener()

    async def shutdown(self) -> None:
        closer = getattr(self.docstore, "close", None)
        if closer is not None:
            await closer()

    def deterministic_llm(self) -> LLMPort:
        """A fresh, seeded MockLLMAdapter.

        `sim/engine.py::advance()` needs this to force determinism during a
        fast-forward regardless of the configured provider -- but `sim/` may
        not import `adapters/` directly (see the guard in
        `tests/test_architecture.py`). This factory is the sanctioned door:
        only `container.py` constructs adapters, and everything else asks for
        one through here.
        """
        from agentshield.adapters.local import MockLLMAdapter

        return MockLLMAdapter(seed=self.settings.sim_seed)

    def describe(self) -> dict[str, str]:
        """Which adapter is behind each port. Surfaced on `/healthz` so a
        deployment can be verified at a glance rather than by inference.
        """
        return {
            "docstore": type(self.docstore).__name__,
            "blobs": type(self.blobs).__name__,
            "bus": type(self.bus).__name__,
            "metrics": type(self.metrics).__name__,
            "queue": type(self.queue).__name__,
            "secrets": type(self.secrets).__name__,
            "llm": type(self.llm).__name__,
            "clock": type(self.clock).__name__,
        }


@lru_cache
def get_container() -> Container:
    """The process-wide container.

    Cached rather than module-level so tests can clear it
    (`get_container.cache_clear()`) and build a container against a temporary
    store. Routes reach it through `deps.py`, never by importing it directly.
    """
    return Container(Settings())
