#!/usr/bin/env python
"""Live Nebius Nemotron smoke test -- the M1 exit gate.

    NEBIUS_API_KEY=... python tasks.py nebius-smoke

Makes TWO real calls to Nebius Token Factory:

  1. Plain text generation -- proves connectivity, auth and the configured
     model id actually serve.
  2. A tool-call round trip -- proves the OpenAI tool dialect reaches the
     model and a parseable tool call comes back.

Prints the exact model id, usage and latency of each call. Exits non-zero on
any failure: this script never fabricates a passing result, and it never
falls back to MockLLM (the adapter forbids it).

Requires the repo's API venv (created by `python tasks.py setup`).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2] / "services" / "api"))

from agentshield.adapters.local.nebius_llm import NebiusAdapter  # noqa: E402
from agentshield.config import Settings  # noqa: E402
from agentshield.ports.llm import (  # noqa: E402
    LLMNotConfigured,
    LLMProviderError,
    LLMResult,
    LLMUnavailable,
)

_TOOLS = [
    {
        "name": "read_file",
        "description": "Read a file from the workspace repository.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path within the repository"}
                },
                "required": ["path"],
            }
        },
    }
]


async def main() -> int:
    settings = Settings()
    if not os.environ.get("NEBIUS_API_KEY") and not settings.nebius_api_key:
        print("NEBIUS_API_KEY is not set. Export it and re-run; no mock fallback exists.")
        return 2

    adapter = NebiusAdapter(settings)
    ok = True

    # 1 -- plain text
    started = time.perf_counter()
    try:
        text_result: LLMResult = await adapter.complete(
            messages=[{"role": "user", "content": "Reply with exactly: NEBIUS-OK"}],
            tools=[],
            model="standard",
            max_tokens=64,
        )
        latency = (time.perf_counter() - started) * 1000
        print("\n[1/2] text generation")
        print(f"  model_id:    {text_result.model_id}")
        print(f"  text:        {text_result.text.strip()[:120]!r}")
        print(f"  usage:       in={text_result.usage.input_tokens} out={text_result.usage.output_tokens}")
        print(f"  stop_reason: {text_result.stop_reason}  latency_ms: {latency:.0f}")
        print(f"  fallback:    {text_result.fallback}  (must be False)")
        ok &= text_result.fallback is False and bool(text_result.text.strip())
    except (LLMNotConfigured, LLMProviderError, LLMUnavailable) as exc:
        print(f"\n[1/2] text generation FAILED: {exc}")
        return 1

    # 2 -- tool round trip
    started = time.perf_counter()
    try:
        tool_result: LLMResult = await adapter.complete(
            messages=[
                {
                    "role": "user",
                    "content": (
                        "You are inspecting a small Python repository to find a failing "
                        "authentication test. Call read_file on the file that most likely "
                        "contains the auth logic."
                    ),
                }
            ],
            tools=_TOOLS,
            model="standard",
            max_tokens=512,
        )
        latency = (time.perf_counter() - started) * 1000
        print("\n[2/2] tool-call round trip")
        print(f"  model_id:    {tool_result.model_id}")
        print(f"  usage:       in={tool_result.usage.input_tokens} out={tool_result.usage.output_tokens}")
        print(f"  stop_reason: {tool_result.stop_reason}  latency_ms: {latency:.0f}")
        if tool_result.tool_calls:
            call = tool_result.tool_calls[0]
            print(f"  tool_call:   {call.name}({json.dumps(call.arguments)[:120]})")
            ok &= call.name == "read_file"
        else:
            print(f"  tool_call:   NONE (text={tool_result.text[:120]!r})")
            print("  NOTE: model answered without a tool call -- check tool dialect support.")
            ok = False
    except (LLMProviderError, LLMUnavailable) as exc:
        print(f"\n[2/2] tool round trip FAILED: {exc}")
        return 1

    print(f"\nSMOKE {'PASSED' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
