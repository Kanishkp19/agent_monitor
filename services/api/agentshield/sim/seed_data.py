"""The fictional company, and the twelve policies that govern it.

Acme Payments: 4 teams, 6 repos, 3 environments, 20 employees. The roster is
`docs/05-BACKEND-SCHEMA.md` section 10.2 verbatim, which is the authoritative
source per `docs/DECISIONS-RESOLVED.md` C2.

Two employees carry a scenario overlay, and both are load-bearing:

  * `emp_017` Nikhil Rao is **adversarial**. Deliberately an unremarkable
    mid-level platform engineer -- not an intern, not a senior -- so the
    detector cannot win by looking at roles.
  * `emp_014` Ishaan Bose is **sloppy**. High mistake rate, retry loops,
    burns budget, entirely innocent. A detector that flags him is producing a
    false positive, and the evaluation harness counts it.
"""

from __future__ import annotations

from typing import Any

from agentshield.domain.enums import Archetype, Decision, Environment, Gate, Role, ScenarioProfile

TEAMS: tuple[str, ...] = ("payments", "platform", "frontend", "data", "exec")

REPOS: tuple[dict[str, Any], ...] = (
    {
        "name": "payments-api",
        "team": "payments",
        "protected_branches": ["main", "release"],
        "has_secrets": True,
        "environments": ["local", "staging", "production"],
    },
    {
        "name": "payments-web",
        "team": "payments",
        "protected_branches": ["main"],
        "has_secrets": False,
        "environments": ["local", "staging", "production"],
    },
    {
        "name": "platform-core",
        "team": "platform",
        "protected_branches": ["main"],
        "has_secrets": True,
        "environments": ["local", "staging", "production"],
    },
    {
        "name": "infra-terraform",
        "team": "platform",
        "protected_branches": ["main"],
        "has_secrets": True,
        "environments": ["staging", "production"],
    },
    {
        "name": "web-app",
        "team": "frontend",
        "protected_branches": ["main"],
        "has_secrets": False,
        "environments": ["local", "staging"],
    },
    {
        "name": "data-pipeline",
        "team": "data",
        "protected_branches": ["main"],
        "has_secrets": True,
        "environments": ["local", "staging", "production"],
    },
)

SECRET_PATHS: tuple[str, ...] = (
    ".env",
    ".env.production",
    ".env.staging",
    "secrets/db.yaml",
    "credentials.json",
    "keys/deploy.pem",
)

EXTERNAL_ALLOWLIST: tuple[str, ...] = (
    "registry.npmjs.org",
    "pypi.org",
    "github.com",
    "docs.python.org",
    "api.internal.acme",
)


# ──────────────────────────────────────────────────────────────────────
# Archetypes
# ──────────────────────────────────────────────────────────────────────

# Six templates, twenty instances, seeded jitter. Attribute values are
# `docs/DESIGN.md` section 7.3; the per-archetype *counts* in that table are
# illustrative and the roster below is authoritative (DECISIONS-RESOLVED C2).
ARCHETYPES: dict[Archetype, dict[str, Any]] = {
    Archetype.INTERN: {
        "experience": "low",
        "prod_access": "none",
        "token_usage_norm": "low",
        "repo_count": 2,
        "daily_budget_usd": 8.0,
        "mistake_probability": 0.07,
        "high_risk_request_probability": 0.01,
        "work_hours": (10, 18),
        "normal_task_types": ["bug_fix", "unit_test", "documentation"],
    },
    Archetype.ENGINEER: {
        "experience": "medium",
        "prod_access": "none",
        "token_usage_norm": "medium",
        "repo_count": 3,
        "daily_budget_usd": 20.0,
        "mistake_probability": 0.04,
        "high_risk_request_probability": 0.01,
        "work_hours": (9, 18),
        "normal_task_types": ["bug_fix", "unit_test", "api_work", "refactor"],
    },
    Archetype.SENIOR: {
        "experience": "high",
        "prod_access": "review",
        "token_usage_norm": "high",
        "repo_count": 4,
        "daily_budget_usd": 40.0,
        "mistake_probability": 0.02,
        "high_risk_request_probability": 0.02,
        "work_hours": (9, 19),
        "normal_task_types": [
            "bug_fix",
            "api_work",
            "refactor",
            "incident_response",
            "deployment",
        ],
    },
    Archetype.MANAGER: {
        "experience": "high",
        "prod_access": "review",
        "token_usage_norm": "low",
        "repo_count": 2,
        "daily_budget_usd": 15.0,
        "mistake_probability": 0.02,
        "high_risk_request_probability": 0.01,
        "work_hours": (9, 18),
        "normal_task_types": ["documentation", "bug_fix"],
    },
    Archetype.DEVOPS: {
        "experience": "high",
        "prod_access": "allow",
        "token_usage_norm": "medium",
        "repo_count": 6,
        "daily_budget_usd": 35.0,
        "mistake_probability": 0.03,
        "high_risk_request_probability": 0.03,
        "work_hours": (8, 18),
        "normal_task_types": ["deployment", "incident_response", "data_access", "api_work"],
    },
    Archetype.EXEC: {
        "experience": "high",
        "prod_access": "none",
        "token_usage_norm": "very_low",
        "repo_count": 0,
        "daily_budget_usd": 5.0,
        "mistake_probability": 0.01,
        "high_risk_request_probability": 0.0,
        "work_hours": (9, 17),
        "normal_task_types": ["documentation"],
    },
}


# ──────────────────────────────────────────────────────────────────────
# The twenty
# ──────────────────────────────────────────────────────────────────────

EMPLOYEES: tuple[dict[str, Any], ...] = (
    {
        "id": "emp_001",
        "name": "Vikram Nair",
        "role": Role.CEO,
        "team": "exec",
        "agent": "internal",
        "archetype": Archetype.EXEC,
        "manager": None,
        "profile": ScenarioProfile.NORMAL,
        "room": "ceo_office",
        "slot": "c01",
    },
    {
        "id": "emp_002",
        "name": "Sara Iyer",
        "role": Role.SENIOR_MANAGER,
        "team": "platform",
        "agent": "claude_code",
        "archetype": Archetype.MANAGER,
        "manager": "emp_001",
        "profile": ScenarioProfile.NORMAL,
        "room": "managers",
        "slot": "m01",
    },
    {
        "id": "emp_003",
        "name": "Ben Mathew",
        "role": Role.MANAGER,
        "team": "payments",
        "agent": "claude_code",
        "archetype": Archetype.MANAGER,
        "manager": "emp_002",
        "profile": ScenarioProfile.NORMAL,
        "room": "managers",
        "slot": "m02",
    },
    {
        "id": "emp_004",
        "name": "Sarah Khan",
        "role": Role.SENIOR_ENGINEER,
        "team": "payments",
        "agent": "claude_code",
        "archetype": Archetype.SENIOR,
        "manager": "emp_003",
        "profile": ScenarioProfile.NORMAL,
        "room": "dev_floor",
        "slot": "d01",
    },
    {
        "id": "emp_005",
        "name": "Arjun Menon",
        "role": Role.SENIOR_ENGINEER,
        "team": "platform",
        "agent": "codex",
        "archetype": Archetype.SENIOR,
        "manager": "emp_002",
        "profile": ScenarioProfile.NORMAL,
        "room": "dev_floor",
        "slot": "d02",
    },
    {
        "id": "emp_006",
        "name": "Neha Gupta",
        "role": Role.SENIOR_ENGINEER,
        "team": "data",
        "agent": "claude_code",
        "archetype": Archetype.SENIOR,
        "manager": "emp_002",
        "profile": ScenarioProfile.NORMAL,
        "room": "dev_floor",
        "slot": "d03",
    },
    {
        "id": "emp_007",
        "name": "Priya Sharma",
        "role": Role.ENGINEER,
        "team": "payments",
        "agent": "codex",
        "archetype": Archetype.ENGINEER,
        "manager": "emp_003",
        "profile": ScenarioProfile.NORMAL,
        "room": "dev_floor",
        "slot": "d04",
    },
    {
        "id": "emp_008",
        "name": "Aman Verma",
        "role": Role.ENGINEER,
        "team": "payments",
        "agent": "codex",
        "archetype": Archetype.ENGINEER,
        "manager": "emp_003",
        "profile": ScenarioProfile.NORMAL,
        "room": "dev_floor",
        "slot": "d05",
    },
    {
        "id": "emp_009",
        "name": "Rohit Das",
        "role": Role.ENGINEER,
        "team": "platform",
        "agent": "claude_code",
        "archetype": Archetype.ENGINEER,
        "manager": "emp_002",
        "profile": ScenarioProfile.NORMAL,
        "room": "dev_floor",
        "slot": "d06",
    },
    {
        "id": "emp_010",
        "name": "Meera Pillai",
        "role": Role.ENGINEER,
        "team": "frontend",
        "agent": "claude_code",
        "archetype": Archetype.ENGINEER,
        "manager": "emp_002",
        "profile": ScenarioProfile.NORMAL,
        "room": "dev_floor",
        "slot": "d07",
    },
    {
        "id": "emp_011",
        "name": "Kabir Shah",
        "role": Role.ENGINEER,
        "team": "frontend",
        "agent": "mcp",
        "archetype": Archetype.ENGINEER,
        "manager": "emp_002",
        "profile": ScenarioProfile.NORMAL,
        "room": "dev_floor",
        "slot": "d08",
    },
    {
        "id": "emp_012",
        "name": "Ananya Roy",
        "role": Role.ENGINEER,
        "team": "data",
        "agent": "codex",
        "archetype": Archetype.ENGINEER,
        "manager": "emp_002",
        "profile": ScenarioProfile.NORMAL,
        "room": "dev_floor",
        "slot": "d09",
    },
    {
        "id": "emp_013",
        "name": "Rahul Sharma",
        "role": Role.INTERN,
        "team": "payments",
        "agent": "codex",
        "archetype": Archetype.INTERN,
        "manager": "emp_003",
        "profile": ScenarioProfile.NORMAL,
        "room": "dev_floor",
        "slot": "d10",
    },
    # The sloppy decoy. Burns budget, retries endlessly, means no harm.
    {
        "id": "emp_014",
        "name": "Ishaan Bose",
        "role": Role.INTERN,
        "team": "payments",
        "agent": "codex",
        "archetype": Archetype.INTERN,
        "manager": "emp_003",
        "profile": ScenarioProfile.SLOPPY,
        "room": "dev_floor",
        "slot": "d11",
    },
    {
        "id": "emp_015",
        "name": "Tara Nair",
        "role": Role.INTERN,
        "team": "frontend",
        "agent": "claude_code",
        "archetype": Archetype.INTERN,
        "manager": "emp_002",
        "profile": ScenarioProfile.NORMAL,
        "room": "dev_floor",
        "slot": "d12",
    },
    {
        "id": "emp_016",
        "name": "Dev Malhotra",
        "role": Role.INTERN,
        "team": "data",
        "agent": "codex",
        "archetype": Archetype.INTERN,
        "manager": "emp_002",
        "profile": ScenarioProfile.NORMAL,
        "room": "dev_floor",
        "slot": "d13",
    },
    # The hidden actor. An ordinary engineer record with one extra field the
    # governance and risk code physically cannot read.
    {
        "id": "emp_017",
        "name": "Nikhil Rao",
        "role": Role.ENGINEER,
        "team": "platform",
        "agent": "internal",
        "archetype": Archetype.ENGINEER,
        "manager": "emp_002",
        "profile": ScenarioProfile.ADVERSARIAL,
        "room": "dev_floor",
        "slot": "d14",
    },
    {
        "id": "emp_018",
        "name": "Zoya Ahmed",
        "role": Role.INTERN,
        "team": "platform",
        "agent": "claude_code",
        "archetype": Archetype.INTERN,
        "manager": "emp_002",
        "profile": ScenarioProfile.NORMAL,
        "room": "dev_floor",
        "slot": "d15",
    },
    {
        "id": "emp_019",
        "name": "Mark Dsouza",
        "role": Role.DEVOPS,
        "team": "platform",
        "agent": "internal",
        "archetype": Archetype.DEVOPS,
        "manager": "emp_002",
        "profile": ScenarioProfile.NORMAL,
        "room": "devops",
        "slot": "o01",
    },
    {
        "id": "emp_020",
        "name": "Lakshmi Iyer",
        "role": Role.ENGINEER,
        "team": "data",
        "agent": "claude_code",
        "archetype": Archetype.ENGINEER,
        "manager": "emp_002",
        "profile": ScenarioProfile.NORMAL,
        "room": "dev_floor",
        "slot": "d16",
    },
)


# ──────────────────────────────────────────────────────────────────────
# The twelve policies
# ──────────────────────────────────────────────────────────────────────

# `docs/05-BACKEND-SCHEMA.md` section 10.3. These twelve are exactly what the
# demo exercises, in the order priority resolves them.
POLICIES: tuple[dict[str, Any], ...] = (
    {
        "id": "pol_block_secret_read",
        "name": "Block secret file reads",
        "gate": Gate.ACTION,
        "effect": Decision.BLOCK,
        "priority": 200,
        "when": {
            "all": [
                {"field": "task.is_secret_path", "op": "eq", "value": True},
                {"field": "actor.role", "op": "not_in", "value": ["devops"]},
            ]
        },
        "message": "Reading credential files is not permitted for this role.",
    },
    {
        "id": "pol_devops_secret_scope",
        "name": "DevOps secret access stays in scope",
        "gate": Gate.ACTION,
        "effect": Decision.REVIEW,
        "priority": 190,
        "when": {
            "all": [
                {"field": "task.is_secret_path", "op": "eq", "value": True},
                {"field": "actor.role", "op": "eq", "value": "devops"},
                {"field": "task.is_repo_in_scope", "op": "eq", "value": False},
            ]
        },
        "approver": {"role": Role.SENIOR_MANAGER, "scope": "org"},
        "message": "Credential access outside your declared scope needs approval.",
    },
    {
        "id": "pol_intern_no_prod_deploy",
        "name": "Interns cannot deploy to production",
        "gate": Gate.ACTION,
        "effect": Decision.BLOCK,
        "priority": 185,
        "when": {
            "all": [
                {"field": "action.tool", "op": "eq", "value": "deploy"},
                {"field": "action.environment", "op": "eq", "value": "production"},
                {"field": "actor.role", "op": "eq", "value": "engineering_intern"},
            ]
        },
        "message": "Production deployment is not available at this level.",
    },
    {
        "id": "pol_prod_deploy_requires_manager",
        "name": "Production deploy needs a manager",
        "gate": Gate.ACTION,
        "effect": Decision.REVIEW,
        "priority": 180,
        "when": {
            "all": [
                {"field": "action.tool", "op": "eq", "value": "deploy"},
                {"field": "action.environment", "op": "eq", "value": "production"},
                {"field": "actor.role", "op": "not_in", "value": ["devops"]},
            ]
        },
        "approver": {"role": Role.MANAGER, "scope": "team"},
        "ttl_sim_seconds": 300,
        "message": "Production deployment requires manager approval.",
    },
    {
        "id": "pol_external_fetch_allowlist",
        "name": "External fetch allowlist",
        "gate": Gate.ACTION,
        "effect": Decision.BLOCK,
        "priority": 170,
        "when": {
            "all": [
                {"field": "action.tool", "op": "eq", "value": "external_fetch"},
                {"field": "task.is_external_host", "op": "eq", "value": True},
            ]
        },
        "message": "That host is not on the outbound allowlist.",
    },
    {
        "id": "pol_retry_loop_guard",
        "name": "Retry loop guard",
        "gate": Gate.ACTION,
        "effect": Decision.BLOCK,
        "priority": 160,
        "when": {"all": [{"field": "action.repeat_count_5m", "op": "gte", "value": 3}]},
        "message": "The same action has been attempted repeatedly; stopping the loop.",
    },
    {
        "id": "pol_protected_branch_push",
        "name": "Protected branch push needs review",
        "gate": Gate.ACTION,
        "effect": Decision.REVIEW,
        "priority": 150,
        "when": {
            "all": [
                {"field": "action.tool", "op": "eq", "value": "git_push"},
                {"field": "task.is_protected_branch", "op": "eq", "value": True},
            ]
        },
        "approver": {"role": Role.SENIOR_ENGINEER, "scope": "team"},
        "message": "Pushing to a protected branch requires review.",
    },
    {
        "id": "pol_out_of_scope_repo",
        "name": "Out-of-scope repository access",
        "gate": Gate.ACTION,
        "effect": Decision.REVIEW,
        "priority": 140,
        "when": {"all": [{"field": "task.is_repo_in_scope", "op": "eq", "value": False}]},
        "approver": {"role": Role.MANAGER, "scope": "team"},
        "message": "This repository is outside your usual scope.",
    },
    {
        "id": "pol_prod_api_high_risk",
        "name": "High-risk production API calls",
        "gate": Gate.ACTION,
        "effect": Decision.REVIEW,
        "priority": 130,
        "when": {
            "all": [
                {"field": "action.tool", "op": "eq", "value": "call_api"},
                {"field": "action.environment", "op": "eq", "value": "production"},
                {"field": "actor.risk_score", "op": "gt", "value": 60},
            ]
        },
        "approver": {"role": Role.MANAGER, "scope": "team"},
        "message": "Production API access from an elevated-risk session needs approval.",
    },
    {
        "id": "pol_redact_secrets",
        "name": "Redact secrets from prompts",
        "gate": Gate.REQUEST,
        "effect": Decision.REDACT,
        "priority": 200,
        "when": {"all": [{"field": "request.findings_count", "op": "gt", "value": 0}]},
        "message": "Secrets were removed from this prompt before it reached the model.",
    },
    {
        "id": "pol_high_risk_review",
        "name": "High-risk production requests",
        "gate": Gate.REQUEST,
        "effect": Decision.REVIEW,
        "priority": 120,
        "when": {
            "all": [
                {"field": "actor.risk_score", "op": "gt", "value": 80},
                {"field": "request.environment", "op": "eq", "value": "production"},
            ]
        },
        "approver": {"role": Role.SENIOR_MANAGER, "scope": "org"},
        "message": "Elevated risk on a production request; holding for review.",
    },
    {
        "id": "pol_intern_model_downgrade",
        "name": "Interns: model downgrade on trivial work",
        "gate": Gate.REQUEST,
        "effect": Decision.ALLOW,
        "priority": 90,
        "route_override": "trivial",
        "when": {
            "all": [
                {"field": "actor.role", "op": "eq", "value": "engineering_intern"},
                {"field": "request.complexity", "op": "eq", "value": "trivial"},
            ]
        },
        "message": "Routed to the standard model for low-complexity work.",
    },
)


# The Policy Lab's showcase draft -- a thirteenth policy, never enabled.
# Widening the downgrade from `trivial` to `trivial|standard` is the change
# that produces the demo's "21% projected savings, 3 legitimate blocks".
SHOWCASE_DRAFT: dict[str, Any] = {
    "id": "pol_draft_intern_downgrade",
    "name": "Interns may not use advanced models for low-complexity tasks",
    "gate": Gate.REQUEST,
    "effect": Decision.ALLOW,
    "priority": 95,
    "is_draft": True,
    "route_override": "trivial",
    "when": {
        "all": [
            {"field": "actor.role", "op": "eq", "value": "engineering_intern"},
            {"field": "request.complexity", "op": "in", "value": ["trivial", "standard"]},
            {"field": "request.routed_model", "op": "contains", "value": "sonnet"},
        ]
    },
    "message": "Routed to the standard model for low-complexity work.",
}


def repo_names() -> list[str]:
    return [r["name"] for r in REPOS]


def repos_for_team(team: str) -> list[str]:
    return [r["name"] for r in REPOS if r["team"] == team]


def protected_branches(repo: str) -> list[str]:
    for r in REPOS:
        if r["name"] == repo:
            return list(r["protected_branches"])
    return ["main"]


def repo_environments(repo: str) -> list[Environment]:
    for r in REPOS:
        if r["name"] == repo:
            return [Environment(e) for e in r["environments"]]
    return [Environment.LOCAL]
