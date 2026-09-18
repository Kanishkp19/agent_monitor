"""DocStorePort -- a DynamoDB-shaped key-value store.

No joins. No scans. No SQL. Every read in the system is one of the enumerated
access patterns A1-A25 in `docs/05-BACKEND-SCHEMA.md` section 3.2; if yours is
not listed, add it to that document with its index *before* writing the code.

This is the least abstracted port on purpose. DynamoDB's data model is adopted,
not hidden: pretending you have joins locally and discovering you don't in
production is the classic portability failure, and it is exactly what this
project is bent around avoiding.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

IndexName = Literal["main", "gsi1", "gsi2"]


class DocItem(BaseModel):
    """One row. `body` carries the entity; the key columns carry the access
    patterns.

    Zero-padding in sort keys is load-bearing: it makes lexicographic ordering
    equal numeric ordering, which is how DynamoDB range queries work.
    """

    pk: str
    sk: str
    gsi1pk: str | None = None
    gsi1sk: str | None = None
    gsi2pk: str | None = None
    gsi2sk: str | None = None
    body: dict[str, Any] = Field(default_factory=dict)
    ttl: int | None = None


class QueryPage(BaseModel):
    items: list[DocItem]
    cursor: str | None = None
    count: int = 0


@runtime_checkable
class DocStorePort(Protocol):
    async def put(self, item: DocItem) -> None: ...

    async def batch_put(self, items: list[DocItem]) -> None: ...

    async def get(self, pk: str, sk: str) -> DocItem | None: ...

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
        """Key-condition query only.

        Exactly one of `sk_prefix` (begins_with) or `sk_between` may be given,
        or neither to fetch the whole partition. Anything that cannot be
        expressed this way is not a supported access pattern.
        """
        ...

    async def update(
        self,
        *,
        pk: str,
        sk: str,
        patch: dict[str, Any],
        condition: str | None = None,
    ) -> DocItem:
        """Apply a patch to one item.

        `patch` may contain the pseudo-operator `{"$add": {field: delta}}` for
        atomic numeric increments -- DynamoDB `ADD`, SQLite `ON CONFLICT DO
        UPDATE` inside a transaction. This is how every aggregate in the product
        is maintained; nothing is ever computed by scanning.
        """
        ...

    async def delete(self, pk: str, sk: str) -> None: ...
