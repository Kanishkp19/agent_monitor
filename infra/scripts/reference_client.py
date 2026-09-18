#!/usr/bin/env python
"""Live Mode reference client.

A full request -> tool -> approval round trip against a real AgentShield, in
under sixty lines of actual logic. This is what an agent developer copies.

    python infra/scripts/reference_client.py --run-id run_7f3a

Note what the client never sends: its own role. It presents a bearer token and
the server decides who that is. An agent cannot escalate itself.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8000/api/v1"


def call(path: str, payload: dict, token: str, run_id: str) -> dict:
    request = urllib.request.Request(
        f"{BASE}{path}?run_id={run_id}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())["data"]
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read() or b"{}")
        print(f"  ! {exc.code} {body.get('error', {}).get('message', '')}")
        raise SystemExit(1) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--token", default="dev-token-1")
    args = parser.parse_args()

    # 1. Ask permission before calling the model. A secret in the prompt comes
    #    back redacted -- the raw value never leaves this process.
    print("gate1: requesting a model call")
    gate1 = call(
        "/ingest/gate1",
        {
            "task_ref": "fix-payment-null-amount",
            "task_type": "bug_fix",
            "complexity": "standard",
            "repo": "payments-api",
            "environment": "production",
            "prompt": "Fix the null amount crash. Key is AKIAIOSFODNN7EXAMPLE",
        },
        args.token,
        args.run_id,
    )
    task_id = gate1["task_id"]
    print(f"  decision={gate1['decision']} model={gate1['routed_model']}")
    print(f"  prompt sent to the model: {gate1['prompt'][:90]}")

    if gate1["decision"] == "block":
        print(f"  blocked: {gate1['reason']}")
        return 0

    # 2. Ask permission before each tool call. This one is fine.
    print("\ngate2: read_file on a source file")
    allowed = call(
        "/ingest/gate2",
        {
            "task_id": task_id,
            "tool": "read_file",
            "args": {"repo": "payments-api", "path": "src/handlers/payment.py"},
            "iteration": 0,
        },
        args.token,
        args.run_id,
    )
    print(f"  decision={allowed['decision']}")

    # 3. This one is not. The refusal is data, not an exception -- your agent
    #    handles it and carries on.
    print("\ngate2: read_file on a credential file")
    blocked = call(
        "/ingest/gate2",
        {
            "task_id": task_id,
            "tool": "read_file",
            "args": {"repo": "payments-api", "path": ".env.production"},
            "iteration": 1,
        },
        args.token,
        args.run_id,
    )
    print(f"  decision={blocked['decision']}  reason={blocked['reason']}")
    print(f"  policies={blocked['policy_ids']}")

    # 4. A production deploy is held for a human.
    print("\ngate2: deploy to production")
    review = call(
        "/ingest/gate2",
        {
            "task_id": task_id,
            "tool": "deploy",
            "args": {"repo": "payments-api", "environment": "production"},
            "iteration": 2,
        },
        args.token,
        args.run_id,
    )
    print(f"  decision={review['decision']}")
    if review.get("approval_id"):
        print(f"  approval {review['approval_id']} is pending")
        print("  poll GET /approvals/{id}, or watch approval.decided on /ws/stream")

    # 5. Report what happened, so it lands in the same Live Feed as everything
    #    the simulator produces.
    call(
        "/ingest/events",
        {
            "task_id": task_id,
            "detail_type": "task.completed",
            "payload": {
                "task_id": task_id,
                "employee_id": "live",
                "status": "completed",
                "tokens_in": 1204,
                "tokens_out": 380,
                "cost_usd": 0.0114,
                "actions_total": 3,
                "actions_blocked": 1,
                "duration_sim_s": 240,
            },
        },
        args.token,
        args.run_id,
    )
    print("\ndone -- these events are now in the Live Feed, tagged source=live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
