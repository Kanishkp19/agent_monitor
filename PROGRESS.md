# Progress

- Replaced the static office-map renderer with a Phaser-powered isometric office.
- Added CC0 Kenney modular-character layers and procedurally drawn desks, chairs, meeting table, plants, and coffee station.
- Verified production build, office-isolation tests, pan/zoom, and employee selection.
- Next: art-direction refinement and richer event-specific character actions if desired.

## Real LLM bots (hybrid provider)

- Added `adapters/local/openai_compat_llm.py` -- OpenAI-compatible adapter covering free
  tiers (Groq default, Gemini OpenAI-compat, OpenRouter): tool-schema translation
  (Converse `inputSchema.json` -> OpenAI `parameters`), token-bucket rate limiter,
  retry/backoff on 429s, mock substitution with `fallback=True` when the key is absent.
- Added `adapters/local/hybrid_llm.py` -- cloud -> Ollama -> Mock chain with a wall-clock
  circuit breaker; a degraded cloud tier falls through to Ollama before settling for mock.
- Wired `LLM_PROVIDER=hybrid` (config, container, `HYBRID_ROUTING` + `PRICE_TABLE` so
  Policy-Lab savings stay real). `.env` defaults: `SIM_LLM_INVOCATION_RATE=0.40`,
  `SIM_MAX_CONCURRENT_SESSIONS=3`.
- Contract suite extended (11 new no-network tests via fake transports); suite now 119
  passing; hermetic `test_default_provider_needs_no_model_installed`.
- Hardened `advance()` drain: bounded-by-progress instead of a fixed 1 s wall slice.
  NOTE: `repro-check` still reports differing streams on this machine even under
  `LLM_PROVIDER=mock` (pre-existing; task ids are wall-clock ULIDs and the advance tail
  is scheduling-dependent) -- tracked as follow-up work, not caused by this change.

## Live Groq wiring (gpt-oss)

- Groq's catalog retired the Llama chat ids; cloud models are now
  `openai/gpt-oss-20b` (trivial/standard) and `openai/gpt-oss-120b` (complex), verified
  for tool calling against the live API.
- `OpenAICompatAdapter` translates the runner's Ollama-lenient history (singular
  `tool_call`, tool results as `role:user` + `tool_call_id`) into strict OpenAI shape;
  strict providers 400 on the raw shapes at the second turn of every session.
- Groq rejects the entire request when the model hallucinates a tool name
  (`tool_use_failed`) -- before the runner's unknown-tool path can engage. The adapter
  now performs the same correction round-trip the runner would have (record call, answer
  `unknown_tool` naming the real tools, re-ask once).
- Retry/backoff honors provider Retry-After (capped 20 s); retries raised 2 -> 4, breaker
  threshold 6 / cooldown 60 s; `reasoning_effort=low` for gpt-oss (hidden thinking was
  eating `max_tokens` and returning empty text); `SIM_MAX_CONCURRENT_SESSIONS=2`.
- Live-measured mix after the fixes: ~90% real Groq calls / ~10% honest mock fallback.
- Cloud errors now carry the provider's diagnostic body (field-level, e.g.
  `tool_use_failed` + `failed_generation`) instead of a bare HTTPStatusError.

## Sandbox playground + real-agent integration

- `api/routes_playground.py` -- no-sign-in governance surface: `Bearer demo-<role>`
  (identity from the credential, never the body), the SAME gate1/gate2 calls, sandbox
  execution on allow, approvals on review. `/playground/context`, `/gate1`, `/gate2`,
  `/tool`, `/tasks/create`, and the universal `/playground/hook/agent`.
- Web: new SANDBOX page (`/sandbox`) -- role/model/repo/env pickers, prompt → Gate 1,
  one-click tool attempts through Gate 2 + sandbox, live trace with decision chips,
  reasons, matched policy ids, routed model/cost, approval ids.
- MCP: `agentshield_gate` tool in `infra/mcp/agentshield_mcp_server.py` -- Claude Code,
  Codex, Antigravity, Cursor, Windsurf (any MCP client) can ask the gate before acting.
- Hooks: `infra/scripts/claude_hook.py` (PreToolUse, native Claude Code JSON contract,
  fail-open on monitoring outage) and `infra/scripts/codex_hook.py` (exit-code contract
  for Codex/shell wrappers). Verified live: intern blocked from prod deploy and
  credential reads; devops deploy allowed; secrets redacted at Gate 1.
- Integration guide: `docs/09-AGENT-INTEGRATION.md` (Claude Code hooks + MCP, Codex
  config, curl for everything else, the 8-tool mapping, what stays simulated).
