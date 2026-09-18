"""The docstore wrapper injected into `risk/`.

An evaluation you can fool is not an evaluation. The detector must never see
the labels it is scored against, and "we were careful" is not a guarantee --
so the read path physically does not exist.

Three layers enforce this, of which this file is the runtime one:

  1. `tests/test_architecture.py` -- `risk/` cannot import `sim/persona.py`,
     `sim/scenarios.py` or `ScenarioProfile`.
  2. **This wrapper** -- any read of a `GT#` key raises, and any `GT#` item
     that somehow appears in a result page is filtered out.
  3. `tests/test_label_isolation.py` -- feature vectors are byte-identical
     with every ground-truth item deleted from the store.

Ground truth is read by exactly one file: `infra/scripts/evaluate.py`, after
the fact, and it uses the unwrapped store.
"""

from __future__ import annotations

from typing import Any

from agentshield.ports.docstore import DocItem, DocStorePort, IndexName, QueryPage

FORBIDDEN_PREFIXES: tuple[str, ...] = ("GT#",)


class LabelLeakError(PermissionError):
    """Raised when the risk engine reaches for a ground-truth key.

    This is a programming error, never a runtime condition to absorb. If it
    fires, a feature is about to be computed from the answer.
    """


class RiskScopedDocStore:
    """Satisfies `DocStorePort`, minus any path to the labels."""

    def __init__(self, inner: DocStorePort) -> None:
        self._inner = inner

    # ── reads: guarded ───────────────────────────────────────────────

    async def get(self, pk: str, sk: str) -> DocItem | None:
        if sk.startswith(FORBIDDEN_PREFIXES):
            raise LabelLeakError(f"risk engine may not read ground truth ({sk})")
        return await self._inner.get(pk, sk)

    async def query(
        self,
        *,
        pk: str,
        sk_prefix: str | None = None,
        sk_between: tuple[str, str] | None = None,
        index: IndexName = "main",
        limit: int = 100,
        cursor: str | None = None,
        ascending: bool = True,
    ) -> QueryPage:
        if sk_prefix and sk_prefix.startswith(FORBIDDEN_PREFIXES):
            raise LabelLeakError(f"risk engine may not read ground truth ({sk_prefix})")
        if sk_between and any(b.startswith(FORBIDDEN_PREFIXES) for b in sk_between):
            raise LabelLeakError("risk engine may not range over ground truth")

        page = await self._inner.query(
            pk=pk,
            sk_prefix=sk_prefix,
            sk_between=sk_between,
            index=index,
            limit=limit,
            cursor=cursor,
            ascending=ascending,
        )
        # A wide range over a partition would otherwise sweep GT# items in
        # alongside events. Belt and braces: the prefix check above catches
        # the deliberate case, this catches the accidental one.
        page.items = [i for i in page.items if not i.sk.startswith(FORBIDDEN_PREFIXES)]
        page.count = len(page.items)
        return page

    # ── writes: pass through ─────────────────────────────────────────
    #
    # The risk engine writes profiles and incidents. It has no reason to write
    # a GT# key, and the guard above means it could not read one back anyway.

    async def put(self, item: DocItem) -> None:
        if item.sk.startswith(FORBIDDEN_PREFIXES):
            raise LabelLeakError("risk engine may not write ground truth")
        await self._inner.put(item)

    async def batch_put(self, items: list[DocItem]) -> None:
        for item in items:
            if item.sk.startswith(FORBIDDEN_PREFIXES):
                raise LabelLeakError("risk engine may not write ground truth")
        await self._inner.batch_put(items)

    async def update(
        self, *, pk: str, sk: str, patch: dict[str, Any], condition: str | None = None
    ) -> DocItem:
        if sk.startswith(FORBIDDEN_PREFIXES):
            raise LabelLeakError("risk engine may not write ground truth")
        return await self._inner.update(pk=pk, sk=sk, patch=patch, condition=condition)

    async def delete(self, pk: str, sk: str) -> None:
        if sk.startswith(FORBIDDEN_PREFIXES):
            raise LabelLeakError("risk engine may not delete ground truth")
        await self._inner.delete(pk, sk)
