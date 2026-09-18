#!/usr/bin/env python
"""Assert no raw secret literal was ever persisted.

Replaces the docs' `grep -r "AKIAIOSFODNN7EXAMPLE" .data/agentshield.db`,
which only worked because SQLite happens to store JSON as text. This inspects
the stored bodies directly, so it works against DynamoDB too.

The answer must be zero. Every time. A single hit means redaction ran after
persistence somewhere, and the guarantee the whole product rests on is gone.

    python tasks.py check-secrets
"""

from __future__ import annotations

import argparse
import json
import sys

from agentshield.deps import Services
from agentshield.scripts._common import heading, resolve_run, run

# The seeded test values the task generator injects into prompts. None are
# live credentials; they exist to prove the scanner fires.
CANARIES = (
    "AKIAIOSFODNN7EXAMPLE",
    "hunter2pass",
    "s3cr3t-staging-pw",
    "api_key=FAKE_NOT_REAL_TEST_TOKEN_1234567890abcdef",
)

# Partitions that could hold a prompt. The blob store is excluded on purpose:
# it is the one place a raw value is *supposed* to live.
PARTITIONS = ("RUN#{run}", "SEQ#{run}", "OUTBOX#{run}")


async def check(services: Services, *, run_id: str | None) -> int:
    resolved = await resolve_run(services, run_id)
    store = services.container.docstore
    hits: list[tuple[str, str, str]] = []

    for template in PARTITIONS:
        page = await store.query(pk=template.format(run=resolved), limit=20_000)
        for item in page.items:
            blob = json.dumps(item.body)
            for canary in CANARIES:
                if canary in blob:
                    hits.append((item.pk, item.sk, canary))

    for task_prefix in ("TASK#",):
        page = await store.query(pk=f"RUN#{resolved}", sk_prefix=task_prefix, limit=5_000)
        for item in page.items:
            blob = json.dumps(item.body)
            for canary in CANARIES:
                if canary in blob:
                    hits.append((item.pk, item.sk, canary))

    heading(f"secret scan: {resolved}")
    if hits:
        print(f"  {len(hits)} RAW SECRET(S) FOUND IN STORAGE:\n")
        for pk, sk, canary in hits[:20]:
            print(f"    {pk} / {sk}  contains {canary}")
        print("\n  Redaction is running after persistence somewhere.")
        return 1

    print("  no raw secret values in persisted events or tasks")
    print("  (raw prompts live only in the blob store, and every read is audited)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    return run(lambda s: check(s, run_id=args.run_id))


if __name__ == "__main__":
    sys.exit(main())
