"""Typed settings for AgentShield.

This is the ONE file permitted to read the `AGENTSHIELD_ENV` variable
(see `docs/DECISIONS-RESOLVED.md` C6). It *loads* the value into a typed
field; it does not branch on it. The only `if settings.env == "aws"` in the
codebase lives in `container.py`.
"""

from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from agentshield.domain.enums import SimSpeed

REPO_ROOT = Path(__file__).resolve().parents[3]

# Deliberately not named `Environment` -- `domain.enums.Environment` is the
# deploy target of a governed action (local/staging/production), which is a
# different axis entirely. Conflating them would be a policy bug waiting to
# happen.
DeploymentEnv = Literal["local", "aws"]
LLMProvider = Literal["mock", "ollama", "bedrock", "hybrid", "nebius"]


class Settings(BaseSettings):
    """Every variable from `docs/02-TRD.md` section 4, typed and validated."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / "services/api/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Core ──────────────────────────────────────────────────────────
    env: DeploymentEnv = Field("local", alias="AGENTSHIELD_ENV")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    # S104: binding all interfaces is required inside a container; App Runner
    # and Docker both route to the published port, not to loopback. Exposure is
    # controlled by the security group and CORS, not by the bind address.
    api_host: str = Field("0.0.0.0", alias="API_HOST")  # noqa: S104
    api_port: int = Field(8000, alias="API_PORT")
    cors_origins_raw: str = Field("http://localhost:5173", alias="CORS_ORIGINS")

    # ── Local adapters ────────────────────────────────────────────────
    sqlite_path: str = Field("./.data/agentshield.db", alias="SQLITE_PATH")
    blob_dir: str = Field("./.data/blobs", alias="BLOB_DIR")
    local_outbox_table: str = Field("outbox", alias="LOCAL_OUTBOX_TABLE")

    # ── LLM ───────────────────────────────────────────────────────────
    llm_provider: LLMProvider = Field("mock", alias="LLM_PROVIDER")
    ollama_base_url: str = Field("http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model_standard: str = Field("qwen2.5-coder:7b", alias="OLLAMA_MODEL_STANDARD")
    ollama_model_trivial: str = Field("qwen2.5-coder:1.5b", alias="OLLAMA_MODEL_TRIVIAL")
    llm_timeout_seconds: int = Field(45, ge=1, alias="LLM_TIMEOUT_SECONDS")
    llm_max_iterations: int = Field(8, ge=1, le=64, alias="LLM_MAX_ITERATIONS")

    # ── Free cloud LLM (OpenAI-compatible: Groq, Gemini, OpenRouter…) ──
    # Only used when LLM_PROVIDER=hybrid. With no key set, the hybrid adapter
    # skips the cloud tier entirely and runs on local Ollama + MockLLM.
    llm_cloud_base_url: str = Field("https://api.groq.com/openai/v1", alias="LLM_CLOUD_BASE_URL")
    llm_cloud_api_key: str = Field("", alias="LLM_CLOUD_API_KEY")
    llm_cloud_model_trivial: str = Field("openai/gpt-oss-20b", alias="LLM_CLOUD_MODEL_TRIVIAL")
    llm_cloud_model_standard: str = Field("openai/gpt-oss-20b", alias="LLM_CLOUD_MODEL_STANDARD")
    llm_cloud_model_complex: str = Field("openai/gpt-oss-120b", alias="LLM_CLOUD_MODEL_COMPLEX")
    llm_cloud_rpm: int = Field(28, ge=1, alias="LLM_CLOUD_RPM")
    llm_cloud_max_retries: int = Field(4, ge=0, le=8, alias="LLM_CLOUD_MAX_RETRIES")
    llm_cloud_breaker_threshold: int = Field(6, ge=1, alias="LLM_CLOUD_BREAKER_THRESHOLD")
    llm_cloud_breaker_cooldown_s: int = Field(60, ge=5, alias="LLM_CLOUD_BREAKER_COOLDOWN_S")

    # ── Nebius Token Factory (NVIDIA Nemotron) ────────────────────────
    # The live provider for Autopilot. Unlike the free-tier cloud settings
    # above, this adapter has NO mock fallback: a qualifying live run either
    # gets a real Nemotron response or the job fails with `LLMUnavailable`.
    nebius_base_url: str = Field("https://api.studio.nebius.com/v1", alias="NEBIUS_BASE_URL")
    nebius_api_key: str = Field("", alias="NEBIUS_API_KEY")
    nebius_model: str = Field("nvidia/nemotron-3-super-120b-a12b", alias="NEBIUS_MODEL")
    nebius_timeout_seconds: int = Field(120, ge=5, alias="NEBIUS_TIMEOUT_SECONDS")
    nebius_max_retries: int = Field(2, ge=0, le=5, alias="NEBIUS_MAX_RETRIES")
    nebius_rpm: int = Field(60, ge=1, alias="NEBIUS_RPM")
    autopilot_demo_token: str = Field("", alias="AUTOPILOT_DEMO_TOKEN")

    # ── Autopilot (live coding engine) ────────────────────────────────
    autopilot_fixtures_dir: str = Field("./infra/fixtures", alias="AUTOPILOT_FIXTURES_DIR")
    autopilot_workspaces_dir: str = Field(
        "./.data/autopilot-workspaces", alias="AUTOPILOT_WORKSPACES_DIR"
    )

    # ── Simulation ────────────────────────────────────────────────────
    sim_seed: int = Field(20260918, ge=0, le=2**31 - 1, alias="SIM_SEED")
    sim_employee_count: int = Field(20, ge=5, le=50, alias="SIM_EMPLOYEE_COUNT")
    sim_max_concurrent_sessions: int = Field(4, ge=1, alias="SIM_MAX_CONCURRENT_SESSIONS")
    sim_tick_sim_seconds: int = Field(60, ge=1, alias="SIM_TICK_SIM_SECONDS")
    sim_default_speed: SimSpeed = Field(SimSpeed.REALTIME, alias="SIM_DEFAULT_SPEED")
    sim_llm_invocation_rate: float = Field(0.08, ge=0.0, le=1.0, alias="SIM_LLM_INVOCATION_RATE")
    sim_scenario_file: str = Field("./scenarios/demo.yaml", alias="SIM_SCENARIO_FILE")
    sim_start_ts: int = Field(1758182400, alias="SIM_START_TS")

    # ── Governance ────────────────────────────────────────────────────
    approval_ttl_sim_seconds: int = Field(300, ge=30, le=86_400, alias="APPROVAL_TTL_SIM_SECONDS")
    retry_loop_threshold: int = Field(3, ge=2, alias="RETRY_LOOP_THRESHOLD")
    redaction_enabled: bool = Field(True, alias="REDACTION_ENABLED")

    # ── Risk ──────────────────────────────────────────────────────────
    risk_weight_static: float = Field(0.35, ge=0.0, le=1.0, alias="RISK_WEIGHT_STATIC")
    risk_weight_behavioural: float = Field(0.40, ge=0.0, le=1.0, alias="RISK_WEIGHT_BEHAVIOURAL")
    risk_weight_ml: float = Field(0.25, ge=0.0, le=1.0, alias="RISK_WEIGHT_ML")
    risk_baseline_window_days: int = Field(14, ge=1, alias="RISK_BASELINE_WINDOW_DAYS")
    risk_min_sessions_for_baseline: int = Field(20, ge=1, alias="RISK_MIN_SESSIONS_FOR_BASELINE")
    risk_incident_threshold: int = Field(70, ge=0, le=100, alias="RISK_INCIDENT_THRESHOLD")
    isolation_forest_estimators: int = Field(200, ge=1, alias="ISOLATION_FOREST_ESTIMATORS")
    isolation_forest_contamination: float = Field(
        0.03, gt=0.0, le=0.5, alias="ISOLATION_FOREST_CONTAMINATION"
    )

    # ── Live Mode ingest ──────────────────────────────────────────────
    ingest_enabled: bool = Field(True, alias="INGEST_ENABLED")
    ingest_tokens_raw: str = Field("", alias="INGEST_TOKENS")
    ingest_rate_limit_per_second: int = Field(100, ge=1, alias="INGEST_RATE_LIMIT_PER_SECOND")

    # ── AWS (ignored entirely when env == "local") ────────────────────
    region: str = Field("ap-south-1", alias="AWS_REGION")
    table: str = Field("agentshield", alias="AGENTSHIELD_TABLE")
    bucket: str = Field("agentshield-artifacts", alias="AGENTSHIELD_BUCKET")
    bus: str = Field("agentshield-bus", alias="AGENTSHIELD_BUS")
    cw_namespace: str = Field("AgentShield", alias="CLOUDWATCH_NAMESPACE")
    bedrock_trivial: str = Field(
        "anthropic.claude-3-5-haiku-20241022-v1:0", alias="BEDROCK_MODEL_TRIVIAL"
    )
    bedrock_standard: str = Field(
        "anthropic.claude-3-5-haiku-20241022-v1:0", alias="BEDROCK_MODEL_STANDARD"
    )
    bedrock_complex: str = Field(
        "anthropic.claude-3-5-sonnet-20241022-v2:0", alias="BEDROCK_MODEL_COMPLEX"
    )
    sqs_queue_url: str = Field("", alias="SQS_QUEUE_URL")

    # ── Derived ───────────────────────────────────────────────────────

    @field_validator("log_level")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @cached_property
    def cors_origins(self) -> list[str]:
        """CORS_ORIGINS is comma-separated. A wildcard is never permitted."""
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]

    @cached_property
    def ingest_tokens(self) -> dict[str, str]:
        """Parse `token:actor_id,token:actor_id` into a lookup.

        A Live Mode caller presents a bearer token; the actor -- and therefore
        the role every policy evaluates against -- is resolved server-side from
        this map. An agent can never assert its own role.
        """
        pairs: dict[str, str] = {}
        for entry in self.ingest_tokens_raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            token, _, actor = entry.partition(":")
            if token and actor:
                pairs[token.strip()] = actor.strip()
        return pairs

    @cached_property
    def sqlite_file(self) -> Path:
        return self._resolve(self.sqlite_path)

    @cached_property
    def blob_path(self) -> Path:
        return self._resolve(self.blob_dir)

    @cached_property
    def scenario_path(self) -> Path:
        return self._resolve(self.sim_scenario_file)

    @cached_property
    def autopilot_fixtures_path(self) -> Path:
        return self._resolve(self.autopilot_fixtures_dir)

    @cached_property
    def autopilot_workspaces_path(self) -> Path:
        return self._resolve(self.autopilot_workspaces_dir)

    @staticmethod
    def _resolve(value: str) -> Path:
        """Resolve a configured path against the repo root, not the CWD.

        The API is launched from `services/api/`, scripts from the repo root,
        and pytest from either. Anchoring on the repo root means all three see
        the same `.data/` directory.
        """
        path = Path(value)
        return path if path.is_absolute() else (REPO_ROOT / path).resolve()
