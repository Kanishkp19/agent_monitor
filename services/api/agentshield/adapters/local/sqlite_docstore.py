"""SQLite implementation of DocStorePort -- a DynamoDB emulator.

This is **not** a relational store with a repository pattern on top. It is one
table with a composite key and two secondary indexes, and the only permitted
queries are the ones DynamoDB would accept:

    pk = ?                                   (whole partition)
    pk = ? AND sk LIKE ? ESCAPE '\\'          (begins_with)
    pk = ? AND sk BETWEEN ? AND ?            (between)

No JOIN. No GROUP BY. No subquery. No unbounded SELECT. If an access pattern
cannot be expressed here it must be added to `docs/05-BACKEND-SCHEMA.md`
section 3.2 with its index *before* the code that needs it is written.

The point of the restriction is that "works locally, breaks in production" is
the classic portability failure, and it is designed out rather than tested for.
"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

import aiosqlite

from agentshield.ports.docstore import DocItem, IndexName, QueryPage

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  pk      TEXT NOT NULL,
  sk      TEXT NOT NULL,
  gsi1pk  TEXT, gsi1sk TEXT,
  gsi2pk  TEXT, gsi2sk TEXT,
  body    TEXT NOT NULL,
  ttl     INTEGER,
  PRIMARY KEY (pk, sk)
);
CREATE INDEX IF NOT EXISTS idx_gsi1 ON items(gsi1pk, gsi1sk);
CREATE INDEX IF NOT EXISTS idx_gsi2 ON items(gsi2pk, gsi2sk);
"""

# Which physical columns back each logical index.
_INDEX_COLUMNS: dict[IndexName, tuple[str, str]] = {
    "main": ("pk", "sk"),
    "gsi1": ("gsi1pk", "gsi1sk"),
    "gsi2": ("gsi2pk", "gsi2sk"),
}

_LIKE_ESCAPE = "\\"


class SqliteDocStore:
    """Single-table key-value store over aiosqlite.

    Durability is traded for write throughput on purpose (`synchronous=NORMAL`):
    the store holds a simulation artefact, and the simulation is reproducible
    from its seed.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    # ── lifecycle ────────────────────────────────────────────────────

    async def connect(self) -> aiosqlite.Connection:
        if self._conn is not None:
            return self._conn
        async with self._lock:
            if self._conn is not None:
                return self._conn
            if self._path != ":memory:":
                Path(self._path).parent.mkdir(parents=True, exist_ok=True)
            conn = await aiosqlite.connect(self._path)
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA journal_mode=WAL;")
            await conn.execute("PRAGMA synchronous=NORMAL;")
            await conn.execute("PRAGMA foreign_keys=OFF;")
            await conn.executescript(_SCHEMA)
            await conn.commit()
            self._conn = conn
            return conn

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ── writes ───────────────────────────────────────────────────────

    async def put(self, item: DocItem) -> None:
        conn = await self.connect()
        async with self._lock:
            await conn.execute(_UPSERT_SQL, _to_row(item))
            await conn.commit()

    async def batch_put(self, items: list[DocItem]) -> None:
        """Write many items in one transaction.

        DynamoDB's BatchWriteItem caps at 25, so callers chunk to 25 to keep the
        two adapters' behaviour identical under load.
        """
        if not items:
            return
        conn = await self.connect()
        async with self._lock:
            await conn.executemany(_UPSERT_SQL, [_to_row(i) for i in items])
            await conn.commit()

    async def update(
        self,
        *,
        pk: str,
        sk: str,
        patch: dict[str, Any],
        condition: str | None = None,
    ) -> DocItem:
        """Merge `patch` into an item's body, atomically.

        Supports one pseudo-operator, mirroring DynamoDB's `ADD`:

            {"$add": {"cost_usd": 0.014, "requests": 1}}

        Missing fields start at zero, so a counter never needs to be created
        before it is incremented. This is how every aggregate in the product is
        maintained -- nothing is computed by scanning.

        `condition` is currently limited to "attribute_exists" semantics; the
        item must already exist unless the patch is purely additive.
        """
        conn = await self.connect()
        async with self._lock:
            async with conn.execute(
                "SELECT pk, sk, gsi1pk, gsi1sk, gsi2pk, gsi2sk, body, ttl "
                "FROM items WHERE pk = ? AND sk = ?",
                (pk, sk),
            ) as cur:
                row = await cur.fetchone()

            if row is None:
                if condition == "attribute_exists":
                    raise KeyError(f"no item at ({pk}, {sk})")
                existing = DocItem(pk=pk, sk=sk, body={})
            else:
                existing = _from_row(row)

            body = dict(existing.body)
            adds = patch.get("$add")
            if isinstance(adds, dict):
                for field, delta in adds.items():
                    body[field] = _add(body.get(field, 0), delta)

            for key, value in patch.items():
                if key == "$add":
                    continue
                body[key] = value

            merged = existing.model_copy(update={"body": body})
            await conn.execute(_UPSERT_SQL, _to_row(merged))
            await conn.commit()
            return merged

    async def delete(self, pk: str, sk: str) -> None:
        conn = await self.connect()
        async with self._lock:
            await conn.execute("DELETE FROM items WHERE pk = ? AND sk = ?", (pk, sk))
            await conn.commit()

    # ── reads ────────────────────────────────────────────────────────

    async def get(self, pk: str, sk: str) -> DocItem | None:
        conn = await self.connect()
        async with conn.execute(
            "SELECT pk, sk, gsi1pk, gsi1sk, gsi2pk, gsi2sk, body, ttl "
            "FROM items WHERE pk = ? AND sk = ?",
            (pk, sk),
        ) as cur:
            row = await cur.fetchone()
        return _from_row(row) if row else None

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
        if sk_prefix is not None and sk_between is not None:
            raise ValueError("pass sk_prefix or sk_between, never both")
        if index not in _INDEX_COLUMNS:
            raise ValueError(f"unknown index {index!r}")

        pk_col, sk_col = _INDEX_COLUMNS[index]
        where = [f"{pk_col} = ?"]
        params: list[Any] = [pk]

        if sk_prefix is not None:
            where.append(f"{sk_col} LIKE ? ESCAPE '{_LIKE_ESCAPE}'")
            params.append(_like_prefix(sk_prefix))
        elif sk_between is not None:
            where.append(f"{sk_col} BETWEEN ? AND ?")
            params.extend(sk_between)

        # Pagination is keyset-based, like DynamoDB's ExclusiveStartKey --
        # never OFFSET, which degrades linearly and can skip rows under writes.
        if cursor:
            where.append(f"{sk_col} > ?" if ascending else f"{sk_col} < ?")
            params.append(_decode_cursor(cursor))

        direction = "ASC" if ascending else "DESC"
        # One extra row tells us whether a next page exists without a COUNT.
        params.append(limit + 1)

        # S608: the only interpolated values are `sk_col` and `direction`, both
        # drawn from module-level literals (`_INDEX_COLUMNS`, and ASC/DESC),
        # after `index` was validated against that same mapping above. Every
        # caller-supplied value is a bound parameter.
        columns = "pk, sk, gsi1pk, gsi1sk, gsi2pk, gsi2sk, body, ttl"
        clauses = " AND ".join(where)
        sql = f"SELECT {columns} FROM items WHERE {clauses} ORDER BY {sk_col} {direction} LIMIT ?"  # noqa: S608

        conn = await self.connect()
        async with conn.execute(sql, params) as cur:
            rows = await cur.fetchall()

        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [_from_row(r) for r in rows]

        next_cursor: str | None = None
        if has_more and items:
            last_sort_value = _sort_value(rows[-1], sk_col)
            if last_sort_value is not None:
                next_cursor = _encode_cursor(last_sort_value)

        return QueryPage(items=items, cursor=next_cursor, count=len(items))

    async def sweep_expired(self, now_ts: int) -> int:
        """Delete items past their TTL.

        DynamoDB does this natively and lazily; locally it is swept on tick so
        the two environments agree about what is readable.
        """
        conn = await self.connect()
        async with self._lock:
            cur = await conn.execute(
                "DELETE FROM items WHERE ttl IS NOT NULL AND ttl <= ?", (now_ts,)
            )
            await conn.commit()
            return cur.rowcount or 0


# ──────────────────────────────────────────────────────────────────────
# Row mapping
# ──────────────────────────────────────────────────────────────────────

_UPSERT_SQL = (
    "INSERT INTO items (pk, sk, gsi1pk, gsi1sk, gsi2pk, gsi2sk, body, ttl) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(pk, sk) DO UPDATE SET "
    "gsi1pk=excluded.gsi1pk, gsi1sk=excluded.gsi1sk, "
    "gsi2pk=excluded.gsi2pk, gsi2sk=excluded.gsi2sk, "
    "body=excluded.body, ttl=excluded.ttl"
)


def _to_row(item: DocItem) -> tuple[Any, ...]:
    return (
        item.pk,
        item.sk,
        item.gsi1pk,
        item.gsi1sk,
        item.gsi2pk,
        item.gsi2sk,
        json.dumps(item.body, separators=(",", ":"), sort_keys=True),
        item.ttl,
    )


def _from_row(row: aiosqlite.Row) -> DocItem:
    return DocItem(
        pk=row["pk"],
        sk=row["sk"],
        gsi1pk=row["gsi1pk"],
        gsi1sk=row["gsi1sk"],
        gsi2pk=row["gsi2pk"],
        gsi2sk=row["gsi2sk"],
        body=json.loads(row["body"]),
        ttl=row["ttl"],
    )


def _sort_value(row: aiosqlite.Row, column: str) -> str | None:
    value = row[column]
    return str(value) if value is not None else None


def _like_prefix(prefix: str) -> str:
    """Escape LIKE wildcards so `EVT#100%` means a literal percent sign.

    Sort keys contain `#` and digits today, but a policy id or repo name could
    one day contain `_`, which LIKE treats as a single-character wildcard. That
    would silently widen a query rather than fail it.
    """
    escaped = (
        prefix.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", f"{_LIKE_ESCAPE}%")
        .replace("_", f"{_LIKE_ESCAPE}_")
    )
    return f"{escaped}%"


def _encode_cursor(sort_key: str) -> str:
    return base64.urlsafe_b64encode(sort_key.encode()).decode()


def _decode_cursor(cursor: str) -> str:
    try:
        return base64.urlsafe_b64decode(cursor.encode()).decode()
    except Exception as exc:
        raise ValueError(f"malformed cursor: {cursor!r}") from exc


def _add(current: Any, delta: Any) -> int | float:
    """Atomic numeric increment, preserving int-ness.

    A counter of `requests` must stay `23`, not become `23.0` -- it crosses a
    JSON boundary into the UI, where the two render differently. `cost_usd`
    stays a float because one operand is.
    """
    a, b = _numeric(current), _numeric(delta)
    if isinstance(a, int) and isinstance(b, int):
        return a + b
    return float(a) + float(b)


def _numeric(value: Any) -> int | float:
    """`$add` operands are numeric. A non-numeric field is a programming error,
    not a runtime condition to absorb silently.
    """
    if isinstance(value, bool):
        raise TypeError("$add does not apply to booleans")
    if isinstance(value, int | float):
        return value
    raise TypeError(f"$add requires a number, got {type(value).__name__}")
