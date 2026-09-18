# AgentShield — Technical Requirements Document

> Architecture rationale lives in `DESIGN.md`. This document is the build sheet: exact versions, exact types, exact environment variables, exact patterns.

---

## 1. Tech Stack

### Backend — `services/api`

| Concern | Package | Version | Purpose |
|---|---|---|---|
| Web framework | `fastapi` | 0.115.x | REST + WebSocket, dependency injection |
| ASGI server | `uvicorn[standard]` | 0.32.x | dev + prod server, `--reload` locally |
| Validation | `pydantic` | 2.9.x | every domain model, every request/response body |
| Settings | `pydantic-settings` | 2.6.x | `config.py`, `.env` loading |
| Local KV store | `aiosqlite` | 0.20.x | DynamoDB-shaped single-table store |
| AWS SDK | `boto3` | 1.35.x | DynamoDB, S3, EventBridge, Bedrock, SQS, Secrets Manager |
| AWS SDK (async) | `aioboto3` | 13.2.x | async paths in AWS adapters only |
| Local LLM | `httpx` | 0.27.x | Ollama HTTP client (inside adapter only) |
| ML | `scikit-learn` | 1.5.x | IsolationForest, StandardScaler |
| Numerics | `numpy` | 2.1.x | feature vectors, z-scores |
| Dataframes | `pandas` | 2.2.x | dataset export only |
| Columnar IO | `pyarrow` | 17.x | Parquet export |
| IDs | `ulid-py` | 1.1.x | sortable ids (`evt_01JAV…`) |
| Scenario config | `pyyaml` | 6.0.x | `scenarios/demo.yaml` |
| Structured logs | `structlog` | 24.4.x | JSON logs matching CloudWatch EMF locally |
| Testing | `pytest`, `pytest-asyncio`, `pytest-benchmark` | 8.3 / 0.24 / 4.0 | unit, contract, e2e |
| AWS mocking | `moto[dynamodb,s3,events]` | 5.0.x | contract tests against the AWS adapters |
| HTTP test client | `httpx` + `fastapi.testclient` | — | API tests |
| Lint/format | `ruff` | 0.7.x | `ruff check` + `ruff format` |
| Types | `mypy` | 1.13.x | `strict = true` on `domain/`, `ports/`, `governance/` |

### Frontend — `apps/web`

| Concern | Package | Version | Purpose |
|---|---|---|---|
| Build | `vite` | 6.0.x | dev server, HMR, bundle |
| UI | `react`, `react-dom` | 19.0.x | |
| Language | `typescript` | 5.6.x | `strict: true`, `noUncheckedIndexedAccess: true` |
| Router | `react-router-dom` | 7.x | 11 routes, nested control-center layout |
| Styling | `tailwindcss` | 4.0.x | CSS-first `@theme` block, see `04-UI-UX-BRIEF.md` |
| Game renderer | `phaser` | 3.90.x | isometric office |
| Client state | `zustand` | 5.0.x | `simStore`, `telemetryStore`, `uiStore` |
| Server state | `@tanstack/react-query` | 5.59.x | all REST reads |
| Virtualised lists | `@tanstack/react-virtual` | 3.10.x | Live Feed (2 000-row buffer) |
| Charts | `recharts` | 2.13.x | exec + cost views |
| Icons | `lucide-react` | 0.460.x | chrome only |
| Dates | `date-fns` | 4.1.x | sim-clock formatting |
| Class merging | `clsx`, `tailwind-merge` | 2.1 / 2.5 | `cn()` helper |
| JSON editor | `@uiw/react-codemirror` + `@codemirror/lang-json` | 4.23 / 6.x | policy editor |
| Testing | `vitest`, `@testing-library/react` | 2.1 / 16.x | |
| Lint | `eslint` + `typescript-eslint` | 9.x / 8.x | |

### Infrastructure

| Concern | Choice | Notes |
|---|---|---|
| Local orchestration | `docker-compose` (optional) + `Makefile` (primary) | `make dev` runs both services without Docker |
| Local model | Ollama `qwen2.5-coder:7b` (Q4_K_M) | ~4.7 GB, comfortable on 16 GB Apple Silicon. `qwen2.5-coder:1.5b` for trivial-complexity routing. |
| AWS packaging | AWS SAM (`infra/aws/template.yaml`) | DynamoDB, S3, EventBridge bus, log group, IAM role, App Runner service |
| AWS compute | App Runner (container from ECR) | one container, no cold-start theatre; ECS Fargate is a drop-in alternative |
| Region | `ap-south-1` default, overridable | Bedrock model availability must be checked per region before demo day |

---

## 2. Repository Layout

See `00-MASTER-PROMPT.md § Project Folder Structure` for the complete tree. It is the authoritative version; do not diverge from it.

---

## 3. Domain Types

### 3.1 Enums (`domain/enums.py` ⇄ `apps/web/src/types/index.ts`)

```python
class Decision(StrEnum):
    ALLOW  = "allow"
    REDACT = "redact"
    REVIEW = "review"
    BLOCK  = "block"

class Gate(IntEnum):
    REQUEST = 1
    ACTION  = 2

class Role(StrEnum):
    INTERN          = "engineering_intern"
    ENGINEER        = "engineer"
    SENIOR_ENGINEER = "senior_engineer"
    MANAGER         = "manager"
    SENIOR_MANAGER  = "senior_manager"
    DEVOPS          = "devops"
    CEO             = "ceo"

class Archetype(StrEnum):
    INTERN = "intern"; ENGINEER = "engineer"; SENIOR = "senior_engineer"
    MANAGER = "manager"; DEVOPS = "devops"; EXEC = "exec"

class ScenarioProfile(StrEnum):      # NEVER exposed via API. Simulation-internal only.
    NORMAL      = "normal"
    SLOPPY      = "sloppy"
    ADVERSARIAL = "adversarial"

class Environment(StrEnum):
    LOCAL = "local"; STAGING = "staging"; PRODUCTION = "production"

class ToolName(StrEnum):
    READ_FILE = "read_file"; EDIT_FILE = "edit_file"; RUN_TESTS = "run_tests"
    GIT_COMMIT = "git_commit"; GIT_PUSH = "git_push"; CALL_API = "call_api"
    DEPLOY = "deploy"; EXTERNAL_FETCH = "external_fetch"

class TaskStatus(StrEnum):
    QUEUED = "queued"; REQUESTING = "requesting"; AWAITING_APPROVAL = "awaiting_approval"
    WORKING = "working"; COMPLETED = "completed"; BLOCKED = "blocked"
    DENIED = "denied"; DENIED_TIMEOUT = "denied_timeout"; FAILED = "failed"

class ApprovalStatus(StrEnum):
    PENDING = "pending"; APPROVED_ONCE = "approved_once"
    APPROVED_SESSION = "approved_session"; DENIED = "denied"; EXPIRED = "expired"

class Sensitivity(StrEnum):
    LOW = "low"; MEDIUM = "medium"; HIGH = "high"; CRITICAL = "critical"

class SimSpeed(IntEnum):
    PAUSED = 0; REALTIME = 1; FAST = 10; TURBO = 100

class Source(StrEnum):
    SIM = "sim"; LIVE = "live"
```

The TypeScript mirror is generated by `packages/contracts/generate.py`; do not hand-write it.

### 3.2 Core models (`domain/models.py`)

```python
class Persona(BaseModel):
    archetype: Archetype
    role: Role
    team: str
    experience: Literal["low", "medium", "high"]
    work_hours: tuple[int, int]                 # (9, 18) local sim hours
    allowed_repositories: list[str]
    normal_task_types: list[str]
    prod_access: Literal["none", "review", "allow"]
    token_usage_norm: Literal["very_low", "low", "medium", "high"]
    daily_budget_usd: float
    mistake_probability: float                  # 0..1
    high_risk_request_probability: float        # 0..1
    llm_invocation_rate: float = 0.08

class Employee(BaseModel):
    id: str                                     # emp_001 .. emp_020
    run_id: str
    name: str
    role: Role
    team: str
    agent_brand: Literal["claude_code", "codex", "internal", "mcp"]
    persona: Persona
    sprite_key: str                             # e.g. "char_04"
    desk: tuple[int, int]                       # tile coords, office map
    manager_id: str | None
    # ── simulation-internal, stripped by every API serialiser ──
    scenario_profile: ScenarioProfile = ScenarioProfile.NORMAL
    scenario_day_offset: int = 0

class EmployeePublic(BaseModel):
    """What the API is allowed to return. scenario_profile is absent by construction."""
    id: str; name: str; role: Role; team: str
    agent_brand: str; sprite_key: str; desk: tuple[int, int]
    manager_id: str | None
    daily_budget_usd: float
    status: TaskStatus
    current_task_id: str | None
    risk_score: int                              # 0..100
    risk_confidence: Literal["low", "normal"]
    today: EmployeeDailyCounters

class EmployeeDailyCounters(BaseModel):
    requests: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    allowed: int = 0
    blocked: int = 0
    review: int = 0
    redacted: int = 0

class Task(BaseModel):
    id: str; run_id: str; employee_id: str
    title: str
    task_type: Literal["bug_fix","unit_test","documentation","api_work",
                       "data_access","deployment","refactor","incident_response"]
    complexity: Literal["trivial", "standard", "complex"]
    repo: str
    environment: Environment
    status: TaskStatus
    routed_model: str | None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    risk_at_request: int = 0
    is_marquee: bool = False                     # → invokes a real LLM
    started_sim_ts: int
    ended_sim_ts: int | None = None
    source: Source = Source.SIM

class SensitiveFinding(BaseModel):
    detector: str                                # "aws_access_key"
    masked: str                                  # "«REDACTED:aws_access_key:a3f9»"
    offset: int
    length: int

class GateRequest(BaseModel):                    # Gate 1 record
    id: str; task_id: str; run_id: str
    est_input_tokens: int; est_output_tokens: int; est_cost_usd: float
    routed_model: str
    findings: list[SensitiveFinding]
    decision: Decision
    reason_code: str                             # "policy" | "budget_exceeded" | "clean"
    matched_policies: list[PolicyMatch]
    context_snapshot: dict                       # full RequestContext, for replay
    latency_ms: float
    sim_ts: int

class AgentAction(BaseModel):                    # Gate 2 record
    id: str; task_id: str; run_id: str
    seq: int                                     # iteration index within the task
    tool: ToolName
    args: dict
    args_digest: str                             # sha256 of normalised args
    target_resource: str                         # "payments-api:.env.production"
    resource_sensitivity: Sensitivity
    environment: Environment
    decision: Decision
    reason_code: str
    matched_policies: list[PolicyMatch]
    approval_id: str | None
    result: ToolResult | None
    context_snapshot: dict
    latency_ms: float
    sim_ts: int

class ToolResult(BaseModel):
    ok: bool
    output: str                                  # truncated to 2000 chars in storage
    error: str | None = None
    duration_ms: int

class PolicyMatch(BaseModel):
    policy_id: str; version: int; effect: Decision; priority: int

class Policy(BaseModel):
    id: str; version: int
    name: str
    gate: Gate
    priority: int = 50
    effect: Decision
    enabled: bool = True
    is_draft: bool = False
    when: dict                                   # DSL node, validated by dsl.validate()
    approver: ApproverSpec | None = None
    ttl_sim_seconds: int = 300
    route_override: str | None = None            # force a cheaper model
    message: str
    created_at: str; created_by: str

class ApproverSpec(BaseModel):
    role: Role
    scope: Literal["team", "org"] = "team"

class Approval(BaseModel):
    id: str; run_id: str; task_id: str; action_id: str
    requester_id: str
    approver_id: str | None
    status: ApprovalStatus
    reason: str                                  # policy message
    risk_at_request: int
    cost_so_far_usd: float
    requested_sim_ts: int
    decided_sim_ts: int | None
    expires_sim_ts: int
    note: str | None

class RiskProfile(BaseModel):
    employee_id: str; run_id: str
    score: int                                   # 0..100 composite
    static: int; behavioural: int; ml: int
    confidence: Literal["low", "normal"]
    top_factors: list[RiskFactor]
    features: dict[str, float]                   # the 12-feature vector
    updated_sim_ts: int

class RiskFactor(BaseModel):
    feature: str
    value: float
    z: float
    contribution: float                          # 0..1 share of the behavioural term
    explanation: str                             # "5.8× normal token usage for this person"

class Incident(BaseModel):
    id: str; run_id: str; employee_id: str
    detector: Literal["composite", "static_critical", "isolation_forest"]
    score: int
    opened_sim_ts: int
    last_seen_sim_ts: int
    status: Literal["open", "acknowledged", "closed"]
    evidence: list[IncidentEvidence]
    summary: str

class IncidentEvidence(BaseModel):
    event_seq: int; sim_ts: int; kind: str; detail: str
```

### 3.3 Gate contexts (`domain/models.py`)

```python
class ActorContext(BaseModel):
    id: str; role: Role; team: str
    seniority: Literal["low", "medium", "high"]
    allowed_repositories: list[str]
    prod_access: Literal["none", "review", "allow"]
    work_hours: tuple[int, int]
    daily_budget_usd: float
    spend_today_usd: float
    risk_score: int
    sessions_today: int
    is_low_confidence: bool

class RequestContext(BaseModel):
    source: Source                               # telemetry only — NOT a policy field
    actor: ActorContext
    task_type: str
    complexity: Literal["trivial","standard","complex"]
    repo: str
    environment: Environment
    prompt_text: str
    prompt_len: int
    requested_model: str | None
    est_input_tokens: int
    est_output_tokens: int
    est_cost_usd: float
    routed_model: str
    findings: list[SensitiveFinding]
    off_hours: bool
    sim_ts: int

class ActionContext(BaseModel):
    source: Source
    actor: ActorContext
    task_id: str
    repo: str
    environment: Environment
    elapsed_sim_s: int
    tokens_so_far: int
    cost_so_far_usd: float
    actions_so_far: int
    blocked_so_far: int
    tool: ToolName
    args: dict
    args_digest: str
    target_resource: str
    resource_sensitivity: Sensitivity
    is_repo_in_scope: bool
    is_secret_path: bool
    is_protected_branch: bool
    is_external_host: bool
    repeat_count_5m: int
    iteration_index: int
    sim_ts: int

class DecisionResult(BaseModel):
    decision: Decision
    reason_code: str
    matched_policies: list[PolicyMatch]
    message: str | None
    approval_id: str | None = None
    route_override: str | None = None
    redacted_text: str | None = None
    latency_ms: float
```

### 3.4 Ports (`ports/*.py`)

```python
class LLMResult(BaseModel):
    text: str
    tool_calls: list[LLMToolCall]
    usage: LLMUsage
    model_id: str
    stop_reason: Literal["end_turn","tool_use","max_tokens","error"]
    fallback: bool = False

class LLMToolCall(BaseModel):
    id: str; name: str; arguments: dict

class LLMUsage(BaseModel):
    input_tokens: int; output_tokens: int

class LLMPort(Protocol):
    async def complete(self, *, messages: list[dict], tools: list[dict],
                       model: str, max_tokens: int = 2048) -> LLMResult: ...

class DocItem(BaseModel):
    pk: str; sk: str
    gsi1pk: str | None = None; gsi1sk: str | None = None
    gsi2pk: str | None = None; gsi2sk: str | None = None
    body: dict
    ttl: int | None = None

class DocStorePort(Protocol):
    async def put(self, item: DocItem) -> None: ...
    async def batch_put(self, items: list[DocItem]) -> None: ...
    async def get(self, pk: str, sk: str) -> DocItem | None: ...
    async def query(self, *, pk: str, sk_prefix: str | None = None,
                    sk_between: tuple[str, str] | None = None,
                    index: Literal["main","gsi1","gsi2"] = "main",
                    limit: int = 100, cursor: str | None = None,
                    ascending: bool = True) -> QueryPage: ...
    async def update(self, *, pk: str, sk: str, patch: dict,
                     condition: str | None = None) -> DocItem: ...

class QueryPage(BaseModel):
    items: list[DocItem]; cursor: str | None; count: int

class EventBusPort(Protocol):
    async def publish(self, envelope: EventEnvelope) -> None: ...
    def subscribe(self, handler: Callable[[EventEnvelope], Awaitable[None]],
                  types: list[str] | None = None) -> None: ...

class BlobStorePort(Protocol):
    async def put_object(self, key: str, data: bytes, content_type: str) -> str: ...
    async def get_object(self, key: str) -> bytes: ...
    async def presign_get(self, key: str, ttl_seconds: int = 900) -> str: ...

class MetricsPort(Protocol):
    def count(self, name: str, value: float = 1, **dims: str) -> None: ...
    def gauge(self, name: str, value: float, **dims: str) -> None: ...
    def timing(self, name: str, ms: float, **dims: str) -> None: ...

class ClockPort(Protocol):
    @property
    def sim_ts(self) -> int: ...
    @property
    def speed(self) -> SimSpeed: ...
    def now_wall(self) -> datetime: ...
    def advance(self, sim_seconds: int) -> int: ...
    def set_speed(self, speed: SimSpeed) -> None: ...
```

### 3.5 Frontend types (`apps/web/src/types/index.ts`)

Generated from `packages/contracts/`. Additional client-only types:

```typescript
export interface OfficeAvatarState {
  employeeId: string
  spriteKey: string
  tile: { x: number; y: number }
  facing: 'n' | 'e' | 's' | 'w'
  fsm: 'idle' | 'walking' | 'working' | 'waiting' | 'blocked' | 'meeting'
  badge: 'none' | 'working' | 'waiting' | 'blocked' | 'anomaly'
  bubble: { text: string; expiresAt: number } | null
}

export interface OfficeSnapshot {
  runId: string
  seq: number                 // resume the WS stream after this
  simTs: number
  speed: 0 | 1 | 10 | 100
  avatars: OfficeAvatarState[]
  pendingApprovals: number
}

export interface WsFrame {
  kind: 'event' | 'batch' | 'progress' | 'snapshot' | 'heartbeat'
  seq: number
  events?: EventEnvelope[]
  progress?: { simDay: number; totalDays: number; eventsGenerated: number }
}

export type ApiError = {
  error: { code: string; message: string; field?: string; details?: unknown }
}
```

---

## 4. Environment Variables

```bash
# ───────────────────────── .env.example ─────────────────────────
# Copy to .env. Everything below works with zero AWS setup.

# ── Core ──────────────────────────────────────────────────────
AGENTSHIELD_ENV=local                 # local | aws   ← the ONLY switch
LOG_LEVEL=INFO
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:5173

# ── Local adapters ────────────────────────────────────────────
SQLITE_PATH=./.data/agentshield.db
BLOB_DIR=./.data/blobs
LOCAL_OUTBOX_TABLE=outbox

# ── LLM ───────────────────────────────────────────────────────
LLM_PROVIDER=mock                     # mock | ollama | bedrock
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL_STANDARD=qwen2.5-coder:7b
OLLAMA_MODEL_TRIVIAL=qwen2.5-coder:1.5b
LLM_TIMEOUT_SECONDS=45
LLM_MAX_ITERATIONS=8                  # agent tool-use loop cap

# ── Simulation ────────────────────────────────────────────────
SIM_SEED=20260918
SIM_EMPLOYEE_COUNT=20
SIM_MAX_CONCURRENT_SESSIONS=4
SIM_TICK_SIM_SECONDS=60               # one tick = one simulated minute
SIM_DEFAULT_SPEED=1                   # 0 | 1 | 10 | 100
SIM_LLM_INVOCATION_RATE=0.08          # fraction of sessions using a real model
SIM_SCENARIO_FILE=./scenarios/demo.yaml

# ── Governance ────────────────────────────────────────────────
APPROVAL_TTL_SIM_SECONDS=300
RETRY_LOOP_THRESHOLD=3                # identical args_digest within 5 sim-minutes
REDACTION_ENABLED=true

# ── Risk ──────────────────────────────────────────────────────
RISK_WEIGHT_STATIC=0.35
RISK_WEIGHT_BEHAVIOURAL=0.40
RISK_WEIGHT_ML=0.25
RISK_BASELINE_WINDOW_DAYS=14
RISK_MIN_SESSIONS_FOR_BASELINE=20
RISK_INCIDENT_THRESHOLD=70
ISOLATION_FOREST_ESTIMATORS=200
ISOLATION_FOREST_CONTAMINATION=0.03

# ── Live Mode ingest ──────────────────────────────────────────
INGEST_ENABLED=true
INGEST_TOKENS=dev-token-1:emp_003,dev-token-2:emp_011   # token:actor_id pairs

# ── AWS (ignored entirely when AGENTSHIELD_ENV=local) ─────────
AWS_REGION=ap-south-1
AGENTSHIELD_TABLE=agentshield
AGENTSHIELD_BUCKET=agentshield-artifacts
AGENTSHIELD_BUS=agentshield-bus
CLOUDWATCH_NAMESPACE=AgentShield
BEDROCK_MODEL_TRIVIAL=anthropic.claude-3-5-haiku-20241022-v1:0
BEDROCK_MODEL_STANDARD=anthropic.claude-3-5-haiku-20241022-v1:0
BEDROCK_MODEL_COMPLEX=anthropic.claude-3-5-sonnet-20241022-v2:0
SQS_QUEUE_URL=
# Credentials come from the standard chain (env, profile, or task role).
# Never put AWS keys in this file.

# ── Frontend (apps/web/.env) ──────────────────────────────────
VITE_API_BASE=http://localhost:8000/api/v1
VITE_WS_URL=ws://localhost:8000/ws/stream
VITE_DEFAULT_ROLE=security_admin      # security_admin | manager | ceo | engineer
```

| Variable | Read by | Notes |
|---|---|---|
| `AGENTSHIELD_ENV` | `container.py` **only** | asserted by an architecture test |
| `LLM_PROVIDER` | `container.py` | `mock` is the default so a fresh clone runs with no model installed |
| `SIM_SEED` | `sim/engine.py` via `Settings` | every `random.Random` is derived from it |
| `INGEST_TOKENS` | `api/routes_ingest.py` | v1 stand-in for real auth; parsed into a dict at startup |
| `RISK_WEIGHT_*` | `risk/scoring.py` | surfaced read-only in the Control Center |

---

## 5. Key Implementation Patterns

### 5.1 The container — the only environment-aware file

```python
# agentshield/container.py
from functools import lru_cache
from agentshield.config import Settings
from agentshield.ports import (LLMPort, DocStorePort, BlobStorePort,
                               EventBusPort, MetricsPort, ClockPort)

class Container:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.clock: ClockPort = SimClock(seed_ts=settings.sim_start_ts,
                                         speed=settings.sim_default_speed)

        if settings.env == "aws":
            from agentshield.adapters.aws import (DynamoDocStore, S3BlobStore,
                                                  EventBridgeBus, CloudWatchEmfMetrics,
                                                  BedrockAdapter)
            self.docstore: DocStorePort = DynamoDocStore(settings.table, settings.region)
            self.blobs: BlobStorePort   = S3BlobStore(settings.bucket, settings.region)
            self.bus: EventBusPort      = EventBridgeBus(settings.bus, settings.region)
            self.metrics: MetricsPort   = CloudWatchEmfMetrics(settings.cw_namespace)
            self.llm: LLMPort           = BedrockAdapter(settings)
        else:
            from agentshield.adapters.local import (SqliteDocStore, FsBlobStore,
                                                    MemoryBus, StdoutMetrics,
                                                    OllamaAdapter, MockLLMAdapter)
            self.docstore = SqliteDocStore(settings.sqlite_path)
            self.blobs    = FsBlobStore(settings.blob_dir)
            self.bus      = MemoryBus(outbox=self.docstore)
            self.metrics  = StdoutMetrics(settings.cw_namespace)
            self.llm      = (OllamaAdapter(settings) if settings.llm_provider == "ollama"
                             else MockLLMAdapter(seed=settings.sim_seed))

@lru_cache
def get_container() -> Container:
    return Container(Settings())
```

Every FastAPI route receives its dependencies through `deps.py`, which reads from `get_container()`. No module-level singletons anywhere else.

### 5.2 SQLite DocStore — DynamoDB emulation

```sql
CREATE TABLE IF NOT EXISTS items (
  pk      TEXT NOT NULL,
  sk      TEXT NOT NULL,
  gsi1pk  TEXT, gsi1sk TEXT,
  gsi2pk  TEXT, gsi2sk TEXT,
  body    TEXT NOT NULL,          -- JSON
  ttl     INTEGER,
  PRIMARY KEY (pk, sk)
);
CREATE INDEX IF NOT EXISTS idx_gsi1 ON items(gsi1pk, gsi1sk);
CREATE INDEX IF NOT EXISTS idx_gsi2 ON items(gsi2pk, gsi2sk);
```

Queries are restricted to `pk = ? AND sk LIKE ?||'%'` or `pk = ? AND sk BETWEEN ? AND ?`. **No other SQL is permitted in the adapter** — no `JOIN`, no `GROUP BY`, no full-table `SELECT`. If an access pattern cannot be expressed this way it must be added to `05-BACKEND-SCHEMA.md §3` with a GSI first.

### 5.3 Bedrock adapter (Converse API)

```python
class BedrockAdapter(LLMPort):
    def __init__(self, s: Settings):
        self._client = boto3.client("bedrock-runtime", region_name=s.region)
        self._models = {"trivial": s.bedrock_trivial,
                        "standard": s.bedrock_standard,
                        "complex": s.bedrock_complex}

    async def complete(self, *, messages, tools, model, max_tokens=2048) -> LLMResult:
        resp = await run_in_threadpool(self._client.converse,
            modelId=self._models.get(model, model),
            messages=[{"role": m["role"],
                       "content": [{"text": m["content"]}]} for m in messages],
            toolConfig={"tools": [{"toolSpec": t} for t in tools]} if tools else None,
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2},
        )
        blocks = resp["output"]["message"]["content"]
        return LLMResult(
            text="".join(b.get("text", "") for b in blocks),
            tool_calls=[LLMToolCall(id=b["toolUse"]["toolUseId"],
                                    name=b["toolUse"]["name"],
                                    arguments=b["toolUse"]["input"])
                        for b in blocks if "toolUse" in b],
            usage=LLMUsage(input_tokens=resp["usage"]["inputTokens"],
                           output_tokens=resp["usage"]["outputTokens"]),
            model_id=self._models.get(model, model),
            stop_reason=_map_stop(resp["stopReason"]),
        )
```

`OllamaAdapter` returns the *same* `LLMResult`, translating Ollama's `message.tool_calls` shape. `MockLLMAdapter` returns seeded, scripted tool sequences per task type — deterministic, instant, free.

### 5.4 Agent runner loop

```python
async def run_agent(task: Task, ctx: Container) -> Task:
    messages = [{"role": "user", "content": build_prompt(task)}]
    for i in range(ctx.settings.llm_max_iterations):
        result = await ctx.llm.complete(messages=messages, tools=TOOL_SCHEMAS,
                                        model=task.complexity)
        await emitter.emit("model.invoked", task=task, usage=result.usage,
                           model=result.model_id, fallback=result.fallback)
        task.tokens_in  += result.usage.input_tokens
        task.tokens_out += result.usage.output_tokens
        task.cost_usd   += price(result.model_id, result.usage)

        if not result.tool_calls:
            return await complete_task(task, result.text)

        for call in result.tool_calls:
            action_ctx = build_action_context(task, call, i)
            decision   = await gate2.evaluate(action_ctx)       # may await approval
            if decision.decision is Decision.BLOCK:
                tool_result = ToolResult(ok=False, output="",
                                         error=f"blocked_by_policy: {decision.message}",
                                         duration_ms=0)
            else:
                tool_result = await sandbox.execute(call, task)
            messages.append(assistant_tool_use(call))
            messages.append(tool_result_message(call.id, tool_result))
    return await fail_task(task, "max_iterations")
```

Note what this does *not* do: it never raises on a block. The refusal goes back to the model as a tool result, and the model's next move is recorded.

### 5.5 Telemetry emitter — the choke point

```python
class TelemetryEmitter:
    async def emit(self, detail_type: str, *, run_id: str, payload: dict,
                   employee_id: str | None = None, task_id: str | None = None,
                   ground_truth: dict | None = None) -> EventEnvelope:
        seq = await self._next_seq(run_id)
        env = EventEnvelope(
            id=f"evt_{ulid.new()}", source=f"agentshield.{self._source}",
            detail_type=detail_type, time=self._clock.now_wall().isoformat(),
            detail=EventDetail(run_id=run_id, seq=seq, sim_ts=self._clock.sim_ts,
                               employee_id=employee_id, task_id=task_id,
                               payload=payload))
        await self._docstore.put(event_item(env))                  # durable
        if ground_truth is not None:                               # separate key!
            await self._docstore.put(ground_truth_item(run_id, seq, ground_truth))
        await self._bus.publish(env)                               # fan-out
        self._ws.broadcast(env)                                    # UI
        self._metrics.count(f"event.{detail_type}", run_id=run_id)
        await self._risk.observe(env)                              # incremental features
        return env
```

`ground_truth` is accepted **only** from `sim/` callers; `governance/` and `agent/` never pass it, and the emitter writes it to a key prefix the risk engine cannot query.

### 5.6 Frontend — WebSocket into Zustand

```typescript
// src/lib/ws.ts
export function connectStream(runId: string) {
  let backoff = 500
  const open = () => {
    const ws = new WebSocket(`${import.meta.env.VITE_WS_URL}?run_id=${runId}` +
                             `&since=${useTelemetry.getState().lastSeq}`)
    ws.onopen    = () => { backoff = 500; useUi.getState().setConnected(true) }
    ws.onmessage = (m) => {
      const frame: WsFrame = JSON.parse(m.data)
      switch (frame.kind) {
        case 'event':
        case 'batch':    useTelemetry.getState().ingest(frame.events ?? []); break
        case 'progress': useSim.getState().setProgress(frame.progress!);     break
        case 'snapshot': useSim.getState().applySnapshot(frame as any);      break
      }
    }
    ws.onclose = () => {
      useUi.getState().setConnected(false)
      setTimeout(open, backoff); backoff = Math.min(backoff * 2, 10_000)
    }
  }
  open()
}
```

`ingest()` appends to a ring buffer capped at 2 000 events, updates `lastSeq`, and pushes visual-relevant events onto the office queue. If `frame.seq - lastSeq > 500`, it triggers a snapshot refetch instead of trying to catch up.

### 5.7 React ⇄ Phaser boundary

```typescript
// src/game/PhaserGame.tsx
export function PhaserGame({ onSelect }: { onSelect: (id: string) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const gameRef = useRef<Phaser.Game | null>(null)

  useEffect(() => {
    if (!ref.current || gameRef.current) return
    gameRef.current = new Phaser.Game({ ...gameConfig, parent: ref.current })
    const bridge = startBridge(gameRef.current, onSelect)   // drains the store
    return () => { bridge.stop(); gameRef.current?.destroy(true); gameRef.current = null }
  }, [])

  return <div ref={ref} className="h-full w-full" />
}
```

React owns mount/unmount and the selection callback. Nothing else crosses the boundary in either direction.

---

## 6. Error Handling

### 6.1 API error envelope

Every non-2xx response from `/api/v1/*`:

```json
{ "error": { "code": "policy_invalid", "message": "Unknown field in condition",
             "field": "when.all[1].field", "details": { "allowed": ["actor.role", "..."] } } }
```

| Code | Status | When |
|---|---|---|
| `validation_failed` | 400 | Pydantic rejection; `field` is the JSON path |
| `policy_invalid` | 400 | DSL validation failure |
| `run_not_found` | 404 | unknown `run_id` |
| `not_found` | 404 | unknown employee/task/approval/policy |
| `approval_already_decided` | 409 | a second decision on the same approval |
| `run_busy` | 409 | control action during a 100× batch |
| `unauthorized` | 401 | bad or missing ingest bearer token |
| `rate_limited` | 429 | ingest over 100 req/s per token |
| `internal_error` | 500 | anything unhandled; logged with a correlation id, never leaked |

### 6.2 Layer-by-layer

| Layer | Failure | Handling |
|---|---|---|
| Adapter (AWS) | throttling, transient | exponential backoff with jitter, 3 attempts, inside the adapter only |
| Adapter (LLM) | timeout / connection refused | fall back to `MockLLM` for that call, `fallback=true` on the event, warning log, UI banner |
| DocStore | write failure after retries | event appended to `.data/dead-letter.jsonl`, `telemetry.degraded` flag set; **governance still proceeds** |
| Gate | unexpected exception | fail **closed**: return `BLOCK` with `reason_code=gate_error`, emit the error event. A governance system that fails open is worse than none. |
| Agent runner | malformed tool call | one correction round-trip, then `task.status=failed` |
| Sim engine | tick overrun | auto-downshift speed, toast to UI |
| API route | uncaught | global exception handler → `internal_error` + correlation id |
| WS | disconnect | client backs off and resumes from `lastSeq`; snapshot if the gap is large |
| React query | fetch error | TanStack retry ×2, then the route's documented error state (`03-APP-FLOW.md`) |
| Phaser | WebGL unavailable | card-grid fallback (`07-OFFICE-SIMULATION.md §11`) |

---

## 7. Performance Requirements

| Operation | Target | How it is achieved |
|---|---|---|
| Gate 1 policy evaluation | p95 < 50 ms | in-memory policy cache, linear scan over ~20 policies, no IO in the hot path |
| Gate 2 policy evaluation | p95 < 50 ms | same |
| Event write | p95 < 15 ms local | single `INSERT OR REPLACE`, WAL mode, no indexes beyond the two GSIs |
| WS frame delivery | < 500 ms from emit to badge change | direct broadcast, no queue hop at 1×/10× |
| 7 sim-days fast-forward | < 20 s | mock LLM, no per-event WS at 100×, batched `batch_put` of 25 items |
| Live Feed at 200 ev/s | no dropped frames | `@tanstack/react-virtual`, 2 000-row ring buffer, 60 ms coalescing window |
| Office render, 20 avatars | ≥ 50 fps | Phaser sprite batching, one texture atlas, static tilemap layer, tweens not per-frame math |
| Policy Lab replay, 24 h | < 5 s | stored context snapshots mean no rebuild-by-join; pure in-process evaluation |
| IsolationForest training | < 10 s on 2 000 sessions | 200 estimators, 12 features, `n_jobs=-1` |
| Cold start to first event | < 10 min on a clean machine | `make setup && make demo`; mock LLM needs no download |

SQLite is opened with `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;` — durability is traded for write throughput deliberately, since the store is a simulation artifact.

---

## 8. Security Checklist

- [ ] No AWS credentials in any file under version control; `.env` is gitignored and `.env.example` contains no secrets
- [ ] Secret redaction runs **before** persistence and before the model payload is built
- [ ] Raw prompts live only in the blob store; every read emits `audit.raw_access`
- [ ] Redaction masks are non-reversible in the UI (`«REDACTED:type:hash4»`)
- [ ] Gates **fail closed** on internal error
- [ ] Live Mode ingest requires a bearer token mapped server-side to an actor; the client cannot assert its own role
- [ ] Ingest rate-limited to 100 req/s per token
- [ ] `source` is excluded from the policy field allowlist so policies cannot diverge between modes
- [ ] `external_fetch` never performs a real network request
- [ ] Policy writes are versioned and append-only
- [ ] CORS restricted to `CORS_ORIGINS`; no wildcard in any environment
- [ ] Structured logs never contain `prompt_text`, tool args for secret paths, or ingest tokens
- [ ] AWS IAM is least-privilege per port (one table, one bucket prefix, one bus, two model ARNs)
- [ ] DynamoDB table has point-in-time recovery enabled; S3 bucket blocks public access and enables SSE-S3
- [ ] `scenario_profile` is stripped by `EmployeePublic` at the type level, not by a serialiser flag that can be forgotten
