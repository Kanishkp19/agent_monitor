"""Gate 2 -- action governance.

Runs before every tool call the agent attempts. This is the gate that matters:
blocking a bad prompt is easy, and blocking `read_file(.env.production)`
mid-session is the actual problem.

There is no `redact` at Gate 2. You cannot partially read a secret file.

Like Gate 1, `evaluate()` is pure -- context in, decision out, no persistence
and no events. The caller owns the approval round-trip and the emission,
which is what keeps the simulator and `/ingest/gate2` on one code path.
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

from agentshield.domain.enums import Decision, Environment, Sensitivity, ToolName
from agentshield.domain.models import ActionContext, DecisionResult, PolicyMatch
from agentshield.governance import precedence
from agentshield.governance.policy_engine import PolicyEngine

logger = logging.getLogger(__name__)

# A path matching any of these is a secret, regardless of who is asking.
SECRET_PATH_PATTERNS: tuple[str, ...] = (
    ".env",
    ".pem",
    ".key",
    "secrets/",
    "credentials",
    "id_rsa",
    ".p12",
    ".pfx",
)

# Hosts `external_fetch` may reach. Everything else is blocked -- the sandbox
# never performs a real request anyway, but the allowlist is what makes the
# attempt legible as a signal rather than as noise.
EXTERNAL_ALLOWLIST: frozenset[str] = frozenset(
    {
        "registry.npmjs.org",
        "pypi.org",
        "github.com",
        "docs.python.org",
        "api.internal.acme",
    }
)

# Static sensitivity, before any policy runs. `docs/DESIGN.md` section 6.1.
_TOOL_SENSITIVITY: dict[ToolName, Sensitivity] = {
    ToolName.READ_FILE: Sensitivity.LOW,
    ToolName.EDIT_FILE: Sensitivity.MEDIUM,
    ToolName.RUN_TESTS: Sensitivity.LOW,
    ToolName.GIT_COMMIT: Sensitivity.MEDIUM,
    ToolName.GIT_PUSH: Sensitivity.HIGH,
    ToolName.CALL_API: Sensitivity.MEDIUM,
    ToolName.DEPLOY: Sensitivity.HIGH,
    ToolName.EXTERNAL_FETCH: Sensitivity.HIGH,
}


class Gate2:
    def __init__(self, *, policies: PolicyEngine) -> None:
        self._policies = policies

    async def evaluate(self, context: ActionContext) -> DecisionResult:
        started = time.perf_counter()
        try:
            return await self._evaluate(context, started)
        except Exception:
            logger.exception(
                "gate2 failed; blocking",
                extra={"actor": context.actor.id, "tool": str(context.tool)},
            )
            return DecisionResult(
                decision=Decision.BLOCK,
                reason_code="gate_error",
                message="The action could not be evaluated and was blocked.",
                latency_ms=_elapsed_ms(started),
            )

    async def _evaluate(self, context: ActionContext, started: float) -> DecisionResult:
        # A session grant short-circuits everything below it. The approver
        # already saw this exact tuple and said yes for the rest of the task.
        matches = await self._policies.match(2, context.policy_view())
        return self._resolve(context, matches, started)

    def _resolve(
        self, context: ActionContext, matches: list[PolicyMatch], started: float
    ) -> DecisionResult:
        ordered = precedence.sort_for_trace(matches)
        effect, attributed = precedence.resolve(matches)

        # Gate 2 has no redact. If a policy somehow carries one, it is treated
        # as a review -- degrading toward more scrutiny, never less.
        if effect is Decision.REDACT:
            effect = Decision.REVIEW

        reason = f"policy:{attributed.policy_id}" if attributed else "clean"
        message = self._message_for(attributed)

        if effect is Decision.BLOCK:
            return DecisionResult(
                decision=Decision.BLOCK,
                reason_code=reason,
                matched_policies=ordered,
                message=message or "This action is not permitted by policy.",
                latency_ms=_elapsed_ms(started),
            )

        if effect is Decision.REVIEW:
            return DecisionResult(
                decision=Decision.REVIEW,
                reason_code=reason,
                matched_policies=ordered,
                message=message or "This action needs approval.",
                latency_ms=_elapsed_ms(started),
            )

        return DecisionResult(
            decision=Decision.ALLOW,
            reason_code="clean" if not matches else "policy_allow",
            matched_policies=ordered,
            message=message,
            latency_ms=_elapsed_ms(started),
        )

    def _message_for(self, match: PolicyMatch | None) -> str | None:
        if match is None:
            return None
        policy = self._policies.cached_policy(match.policy_id)
        return policy.message if policy else None

    def approver_for(self, match: PolicyMatch | None):  # type: ignore[no-untyped-def]
        if match is None:
            return None
        policy = self._policies.cached_policy(match.policy_id)
        return policy.approver if policy else None

    def ttl_for(self, match: PolicyMatch | None, default: int) -> int:
        if match is None:
            return default
        policy = self._policies.cached_policy(match.policy_id)
        return policy.ttl_sim_seconds if policy else default


# ──────────────────────────────────────────────────────────────────────
# Resource resolution -- step 1 of the algorithm
# ──────────────────────────────────────────────────────────────────────


def resolve_resource(
    tool: ToolName,
    args: dict[str, object],
    *,
    repo: str,
    environment: Environment,
    allowed_repositories: list[str],
    protected_branches: list[str] | None = None,
) -> dict[str, object]:
    """Turn a tool call into the facts a policy can reason about.

    Everything a Gate 2 policy reads about the *action* is derived here, once,
    so the same tool call always produces the same flags no matter which
    entry point built the context.
    """
    target_repo = str(args.get("repo") or repo)
    path = str(args.get("path") or "")
    branch = str(args.get("branch") or "")
    url = str(args.get("url") or "")
    action_env = Environment(str(args.get("environment") or environment))

    is_secret_path = _is_secret_path(path)
    is_external_host = bool(url) and not _host_allowed(url)
    is_protected = bool(branch) and branch in (protected_branches or [])
    in_scope = not allowed_repositories or target_repo in allowed_repositories

    return {
        "target_resource": _describe_target(tool, target_repo, path, branch, url, args),
        "resource_sensitivity": _sensitivity(
            tool, action_env, is_secret_path=is_secret_path, is_protected=is_protected
        ),
        "environment": action_env,
        "repo": target_repo,
        "is_repo_in_scope": in_scope,
        "is_secret_path": is_secret_path,
        "is_protected_branch": is_protected,
        "is_external_host": is_external_host,
    }


def _is_secret_path(path: str) -> bool:
    if not path:
        return False
    lowered = path.lower()
    return any(marker in lowered for marker in SECRET_PATH_PATTERNS)


def _host_allowed(url: str) -> bool:
    try:
        host = urlparse(url if "//" in url else f"//{url}").hostname or ""
    except ValueError:
        return False
    host = host.lower()
    return any(host == a or host.endswith(f".{a}") for a in EXTERNAL_ALLOWLIST)


def _describe_target(
    tool: ToolName,
    repo: str,
    path: str,
    branch: str,
    url: str,
    args: dict[str, object],
) -> str:
    """A stable, human-readable name for what is about to be touched.

    Shown on the approval card and in the Live Feed, so it has to read well at
    a glance: `payments-api:.env.production`, not a dict.
    """
    if tool is ToolName.EXTERNAL_FETCH:
        return url or "external"
    if tool is ToolName.CALL_API:
        return f"{args.get('service', 'api')}:{args.get('path', '/')}"
    if tool is ToolName.DEPLOY:
        return f"{repo}:{args.get('environment', 'local')}"
    if tool in (ToolName.GIT_PUSH, ToolName.GIT_COMMIT):
        return f"{repo}@{branch or 'HEAD'}"
    if tool is ToolName.RUN_TESTS:
        return f"{repo}:{args.get('suite', 'all')}"
    return f"{repo}:{path}" if path else repo


def _sensitivity(
    tool: ToolName,
    environment: Environment,
    *,
    is_secret_path: bool,
    is_protected: bool,
) -> Sensitivity:
    """Static sensitivity, before behaviour is considered.

    A secret path is critical whoever is reading it, and a production deploy
    is critical whoever is running it. This is the term that works from the
    very first event, before any baseline exists.
    """
    if is_secret_path:
        return Sensitivity.CRITICAL
    if tool is ToolName.DEPLOY and environment is Environment.PRODUCTION:
        return Sensitivity.CRITICAL
    if is_protected:
        return Sensitivity.HIGH
    if environment is Environment.PRODUCTION:
        base = _TOOL_SENSITIVITY.get(tool, Sensitivity.LOW)
        return Sensitivity.HIGH if base is Sensitivity.MEDIUM else base
    return _TOOL_SENSITIVITY.get(tool, Sensitivity.LOW)


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000.0
