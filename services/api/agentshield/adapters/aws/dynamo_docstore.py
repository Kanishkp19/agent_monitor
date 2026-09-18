"""DynamoDB implementation of DocStorePort.

The counterpart to `SqliteDocStore`. Both pass the same contract suite, which
is what makes the AWS switch a thirty-minute job rather than a weekend: a
change that breaks parity fails CI before it reaches a deploy.

boto3 is used synchronously and offloaded with `asyncio.to_thread` rather than
via aioboto3. Two reasons: moto instruments botocore's synchronous stack, so
the contract tests are trustworthy; and DynamoDB calls are single-digit
milliseconds, so a thread hop costs less than the aiobotocore dependency risk.
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from agentshield.adapters.aws._serde import from_dynamo, to_dynamo
from agentshield.ports.docstore import DocItem, IndexName, QueryPage

# Which key attributes back each logical index -- identical mapping to the
# SQLite adapter's `_INDEX_COLUMNS`.
_INDEX_KEYS: dict[IndexName, tuple[str, str]] = {
    "main": ("pk", "sk"),
    "gsi1": ("gsi1pk", "gsi1sk"),
    "gsi2": ("gsi2pk", "gsi2sk"),
}

_BATCH_LIMIT = 25  # DynamoDB BatchWriteItem hard cap


class DynamoDocStore:
    def __init__(self, table: str, region: str, client: Any = None) -> None:
        self._resource = boto3.resource("dynamodb", region_name=region)
        self._table = client if client is not None else self._resource.Table(table)

    # ── writes ───────────────────────────────────────────────────────

    async def put(self, item: DocItem) -> None:
        await asyncio.to_thread(self._table.put_item, Item=_to_attrs(item))

    async def batch_put(self, items: list[DocItem]) -> None:
        if not items:
            return
        for start in range(0, len(items), _BATCH_LIMIT):
            chunk = items[start : start + _BATCH_LIMIT]
            await asyncio.to_thread(self._write_chunk, chunk)

    def _write_chunk(self, chunk: list[DocItem]) -> None:
        with self._table.batch_writer() as batch:
            for item in chunk:
                batch.put_item(Item=_to_attrs(item))

    async def update(
        self,
        *,
        pk: str,
        sk: str,
        patch: dict[str, Any],
        condition: str | None = None,
    ) -> DocItem:
        """One atomic UpdateItem.

        `$add` becomes `SET body.#f = if_not_exists(body.#f, :zero) + :delta`.
        DynamoDB's native `ADD` only works on top-level attributes, and `body`
        is a Map, so this is the nested-path equivalent -- still a single
        atomic write, which is what matters: counters are incremented
        concurrently from every gate decision.
        """
        set_parts: list[str] = []
        names: dict[str, str] = {}
        values: dict[str, Any] = {}

        adds = patch.get("$add")
        if isinstance(adds, dict):
            values[":zero"] = 0
            for index, (field, delta) in enumerate(sorted(adds.items())):
                alias, value_key = f"#a{index}", f":a{index}"
                names[alias] = field
                values[value_key] = to_dynamo(delta)
                set_parts.append(f"body.{alias} = if_not_exists(body.{alias}, :zero) + {value_key}")

        for index, (field, value) in enumerate(
            sorted((k, v) for k, v in patch.items() if k != "$add")
        ):
            alias, value_key = f"#s{index}", f":s{index}"
            names[alias] = field
            values[value_key] = to_dynamo(value)
            set_parts.append(f"body.{alias} = {value_key}")

        if not set_parts:
            existing = await self.get(pk, sk)
            if existing is None:
                raise KeyError(f"no item at ({pk}, {sk})")
            return existing

        kwargs: dict[str, Any] = {
            "Key": {"pk": pk, "sk": sk},
            # `body` may not exist yet on a first increment; create it empty so
            # the nested SET has somewhere to land.
            "UpdateExpression": "SET " + ", ".join(set_parts),
            "ExpressionAttributeNames": names,
            "ExpressionAttributeValues": values,
            "ReturnValues": "ALL_NEW",
        }
        if condition == "attribute_exists":
            kwargs["ConditionExpression"] = "attribute_exists(pk)"

        try:
            response = await asyncio.to_thread(self._table.update_item, **kwargs)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code == "ConditionalCheckFailedException":
                raise KeyError(f"no item at ({pk}, {sk})") from exc
            if code == "ValidationException":
                # The `body` map did not exist. Seed it, then retry once.
                await asyncio.to_thread(
                    self._table.update_item,
                    Key={"pk": pk, "sk": sk},
                    UpdateExpression="SET body = if_not_exists(body, :empty)",
                    ExpressionAttributeValues={":empty": {}},
                )
                response = await asyncio.to_thread(self._table.update_item, **kwargs)
            else:
                raise

        return _from_attrs(response["Attributes"])

    async def delete(self, pk: str, sk: str) -> None:
        await asyncio.to_thread(self._table.delete_item, Key={"pk": pk, "sk": sk})

    # ── reads ────────────────────────────────────────────────────────

    async def get(self, pk: str, sk: str) -> DocItem | None:
        response = await asyncio.to_thread(self._table.get_item, Key={"pk": pk, "sk": sk})
        raw = response.get("Item")
        return _from_attrs(raw) if raw else None

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
        if index not in _INDEX_KEYS:
            raise ValueError(f"unknown index {index!r}")

        pk_attr, sk_attr = _INDEX_KEYS[index]
        condition = Key(pk_attr).eq(pk)
        if sk_prefix is not None:
            condition = condition & Key(sk_attr).begins_with(sk_prefix)
        elif sk_between is not None:
            condition = condition & Key(sk_attr).between(*sk_between)

        kwargs: dict[str, Any] = {
            "KeyConditionExpression": condition,
            "Limit": limit,
            "ScanIndexForward": ascending,
        }
        if index != "main":
            kwargs["IndexName"] = index
        if cursor:
            kwargs["ExclusiveStartKey"] = _decode_cursor(cursor)

        response = await asyncio.to_thread(self._table.query, **kwargs)
        items = [_from_attrs(raw) for raw in response.get("Items", [])]
        last_key = response.get("LastEvaluatedKey")

        return QueryPage(
            items=items,
            cursor=_encode_cursor(last_key) if last_key else None,
            count=len(items),
        )

    async def sweep_expired(self, now_ts: int) -> int:
        """DynamoDB expires TTL items natively, within about 48 hours.

        Returning zero keeps the port surface identical without pretending to
        do work the platform already does.
        """
        return 0


# ──────────────────────────────────────────────────────────────────────
# Attribute mapping
# ──────────────────────────────────────────────────────────────────────


def _to_attrs(item: DocItem) -> dict[str, Any]:
    attrs: dict[str, Any] = {"pk": item.pk, "sk": item.sk, "body": to_dynamo(item.body)}
    for name in ("gsi1pk", "gsi1sk", "gsi2pk", "gsi2sk"):
        value = getattr(item, name)
        # DynamoDB indexes ignore items missing a key attribute; writing an
        # explicit null would be an error, so omit instead.
        if value is not None:
            attrs[name] = value
    if item.ttl is not None:
        attrs["ttl"] = item.ttl
    return attrs


def _from_attrs(attrs: dict[str, Any]) -> DocItem:
    return DocItem(
        pk=attrs["pk"],
        sk=attrs["sk"],
        gsi1pk=attrs.get("gsi1pk"),
        gsi1sk=attrs.get("gsi1sk"),
        gsi2pk=attrs.get("gsi2pk"),
        gsi2sk=attrs.get("gsi2sk"),
        body=from_dynamo(attrs.get("body") or {}),
        ttl=int(attrs["ttl"]) if attrs.get("ttl") is not None else None,
    )


def _encode_cursor(last_key: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(from_dynamo(last_key), sort_keys=True).encode()
    ).decode()


def _decode_cursor(cursor: str) -> dict[str, Any]:
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception as exc:
        raise ValueError(f"malformed cursor: {cursor!r}") from exc
