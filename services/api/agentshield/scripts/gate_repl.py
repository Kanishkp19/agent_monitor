#!/usr/bin/env python
"""Interactive gate console.

Probe policy decisions by hand, without a simulation running. This is the
fastest way to answer "would this be blocked?" and the fastest way to see
*why*, because it prints the matched policies rather than just the verdict.

    python tasks.py gate-repl

    > gate1 intern trivial payments-api production "fix the bug, key is AKIA..."
    > gate2 intern read_file payments-api .env.production
    > gate2 devops deploy payments-api production
    > policies 2
"""

from __future__ import annotations

import shlex
import sys

from agentshield.agent.router import cost_of, estimate_tokens, route
from agentshield.deps import Services
from agentshield.domain.enums import Environment, Role, ToolName
from agentshield.domain.models import (
    ActionContext,
    ActorContext,
    RequestContext,
    digest_args,
)
from agentshield.governance.gate2 import resolve_resource
from agentshield.scripts._common import run
from agentshield.sim.seed_data import protected_branches, repos_for_team

ROLES: dict[str, Role] = {
    "intern": Role.INTERN,
    "engineer": Role.ENGINEER,
    "senior": Role.SENIOR_ENGINEER,
    "manager": Role.MANAGER,
    "senior_manager": Role.SENIOR_MANAGER,
    "devops": Role.DEVOPS,
    "ceo": Role.CEO,
}

TEAM_FOR: dict[Role, str] = {
    Role.INTERN: "payments",
    Role.ENGINEER: "payments",
    Role.SENIOR_ENGINEER: "payments",
    Role.MANAGER: "payments",
    Role.SENIOR_MANAGER: "platform",
    Role.DEVOPS: "platform",
    Role.CEO: "exec",
}

HELP = """\
commands
  gate1 <role> <complexity> <repo> <env> "<prompt>"
  gate2 <role> <tool> <repo> <path-or-arg> [env]
  policies [1|2]
  risk <0-100>          set the actor risk score used by subsequent calls
  help
  quit\
"""


def actor_for(role: Role, risk: int = 0) -> ActorContext:
    team = TEAM_FOR.get(role, "payments")
    return ActorContext(
        id="emp_repl",
        role=role,
        team=team,
        seniority="low" if role is Role.INTERN else "medium",
        allowed_repositories=repos_for_team(team),
        prod_access="allow" if role is Role.DEVOPS else "none",
        daily_budget_usd=8.0 if role is Role.INTERN else 20.0,
        risk_score=risk,
    )


async def repl(services: Services) -> int:
    await services.seeder.seed_policies()
    print("AgentShield gate console.  'help' for commands, 'quit' to exit.\n")
    risk = 0

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not line:
            continue
        if line in ("quit", "exit"):
            return 0
        if line == "help":
            print(HELP)
            continue

        try:
            parts = shlex.split(line)
        except ValueError as exc:
            print(f"  ! {exc}")
            continue

        command, args = parts[0], parts[1:]

        try:
            if command == "risk" and args:
                risk = max(0, min(100, int(args[0])))
                print(f"  actor risk score = {risk}")
            elif command == "policies":
                await _show_policies(services, int(args[0]) if args else None)
            elif command == "gate1":
                await _gate1(services, args, risk)
            elif command == "gate2":
                await _gate2(services, args, risk)
            else:
                print(f"  ? unknown command {command!r}. 'help' for commands.")
        except Exception as exc:
            print(f"  ! {type(exc).__name__}: {exc}")


async def _show_policies(services: Services, gate: int | None) -> None:
    policies = await services.policies.list_all(gate=gate, include_drafts=True)
    for policy in policies:
        state = "draft" if policy.is_draft else ("on" if policy.enabled else "off")
        print(
            f"  gate{int(policy.gate)} {str(policy.effect).upper():<7} "
            f"p{policy.priority:<4} {policy.id:<38} {state}"
        )


async def _gate1(services: Services, args: list[str], risk: int) -> None:
    role = ROLES[args[0]]
    complexity = args[1]
    repo = args[2]
    environment = Environment(args[3])
    prompt = args[4] if len(args) > 4 else ""

    actor = actor_for(role, risk)
    est_in, est_out = estimate_tokens("bug_fix", complexity, len(prompt))  # type: ignore[arg-type]
    routed = route(complexity)  # type: ignore[arg-type]

    context = RequestContext(
        actor=actor,
        task_type="bug_fix",
        complexity=complexity,  # type: ignore[arg-type]
        repo=repo,
        environment=environment,
        prompt_text=prompt,
        prompt_len=len(prompt),
        est_input_tokens=est_in,
        est_output_tokens=est_out,
        est_cost_usd=cost_of(routed, est_in, est_out),
        routed_model=routed,
    )

    result = await services.gate1.evaluate(context)
    findings = ",".join(f.detector for f in context.findings) or "none"

    print(
        f"  decision={result.decision!s:<7} findings=[{findings}] "
        f"routed={_short(context.routed_model)} est=${context.est_cost_usd:.4f} "
        f"({result.latency_ms:.1f}ms)"
    )
    _print_matches(result)
    if result.redacted_text:
        print(f"  redacted: {result.redacted_text[:110]}")


async def _gate2(services: Services, args: list[str], risk: int) -> None:
    role = ROLES[args[0]]
    tool = ToolName(args[1])
    repo = args[2]
    target = args[3] if len(args) > 3 else ""
    environment = Environment(args[4]) if len(args) > 4 else Environment.LOCAL

    actor = actor_for(role, risk)
    tool_args = _args_for(tool, repo, target, environment)

    resolved = resolve_resource(
        tool,
        tool_args,
        repo=repo,
        environment=environment,
        allowed_repositories=actor.allowed_repositories,
        protected_branches=protected_branches(repo),
    )

    context = ActionContext(
        actor=actor,
        task_id="task_repl",
        repo=repo,
        environment=Environment(str(resolved["environment"])),
        tool=tool,
        args=tool_args,
        args_digest=digest_args(tool, tool_args),
        target_resource=str(resolved["target_resource"]),
        resource_sensitivity=resolved["resource_sensitivity"],  # type: ignore[arg-type]
        is_repo_in_scope=bool(resolved["is_repo_in_scope"]),
        is_secret_path=bool(resolved["is_secret_path"]),
        is_protected_branch=bool(resolved["is_protected_branch"]),
        is_external_host=bool(resolved["is_external_host"]),
    )

    result = await services.gate2.evaluate(context)
    print(
        f"  decision={result.decision!s:<7} target={context.target_resource} "
        f"sensitivity={context.resource_sensitivity} ({result.latency_ms:.1f}ms)"
    )
    _print_matches(result)
    if result.message:
        print(f"  message: {result.message}")


def _args_for(
    tool: ToolName, repo: str, target: str, environment: Environment
) -> dict[str, object]:
    if tool is ToolName.EXTERNAL_FETCH:
        return {"url": target}
    if tool is ToolName.DEPLOY:
        return {"repo": repo, "environment": str(environment)}
    if tool in (ToolName.GIT_PUSH, ToolName.GIT_COMMIT):
        return {"repo": repo, "branch": target or "main", "message": "repl"}
    if tool is ToolName.CALL_API:
        return {
            "service": target or "billing",
            "method": "GET",
            "path": "/v1",
            "environment": str(environment),
        }
    if tool is ToolName.RUN_TESTS:
        return {"repo": repo, "suite": target or "unit"}
    return {"repo": repo, "path": target}


def _print_matches(result: object) -> None:
    matches = getattr(result, "matched_policies", [])
    for match in matches:
        print(
            f"    matched {match.policy_id} (v{match.version}, p{match.priority}) "
            f"-> {str(match.effect).upper()}"
        )


def _short(model_id: str) -> str:
    for name in ("haiku", "sonnet", "qwen", "mock"):
        if name in model_id:
            return name
    return model_id


def main() -> int:
    return run(repl)


if __name__ == "__main__":
    sys.exit(main())
