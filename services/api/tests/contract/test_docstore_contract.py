"""DocStorePort contract -- runs against SQLite and DynamoDB.

Every access pattern the product uses (A1-A25 in
`docs/05-BACKEND-SCHEMA.md` section 3.2) reduces to one of the operations
below. If a behaviour differs between the two stores, it surfaces here rather
than in production.
"""

from __future__ import annotations

from typing import Any

import pytest

from agentshield.ports.docstore import DocItem

pytestmark = pytest.mark.contract


async def test_put_and_get_round_trip(docstore: Any) -> None:
    item = DocItem(pk="RUN#r1", sk="EMP#emp_017", body={"name": "Nikhil Rao", "risk": 84})
    await docstore.put(item)

    fetched = await docstore.get("RUN#r1", "EMP#emp_017")
    assert fetched is not None
    assert fetched.body == {"name": "Nikhil Rao", "risk": 84}


async def test_get_missing_returns_none(docstore: Any) -> None:
    assert await docstore.get("RUN#nope", "EMP#nope") is None


async def test_put_overwrites(docstore: Any) -> None:
    await docstore.put(DocItem(pk="RUN#r1", sk="META", body={"day": 1}))
    await docstore.put(DocItem(pk="RUN#r1", sk="META", body={"day": 2}))

    fetched = await docstore.get("RUN#r1", "META")
    assert fetched is not None and fetched.body == {"day": 2}


async def test_batch_put_exceeds_dynamo_chunk_limit(docstore: Any) -> None:
    """60 items crosses DynamoDB's 25-per-batch cap twice over."""
    await docstore.batch_put(
        [DocItem(pk="RUN#r1", sk=f"EVT#{i:012d}", body={"i": i}) for i in range(60)]
    )
    page = await docstore.query(pk="RUN#r1", sk_prefix="EVT#", limit=100)
    assert page.count == 60


async def test_query_begins_with(docstore: Any) -> None:
    await docstore.batch_put(
        [
            DocItem(pk="RUN#r1", sk="EMP#emp_001", body={}),
            DocItem(pk="RUN#r1", sk="EMP#emp_002", body={}),
            DocItem(pk="RUN#r1", sk="TASK#0000000001#t1", body={}),
        ]
    )
    page = await docstore.query(pk="RUN#r1", sk_prefix="EMP#")
    assert [i.sk for i in page.items] == ["EMP#emp_001", "EMP#emp_002"]


async def test_query_between(docstore: Any) -> None:
    """A10 -- the Live Feed's event page."""
    await docstore.batch_put(
        [DocItem(pk="RUN#r1", sk=f"EVT#{i:012d}", body={"i": i}) for i in range(1, 11)]
    )
    page = await docstore.query(pk="RUN#r1", sk_between=("EVT#000000000003", "EVT#000000000006"))
    assert [i.body["i"] for i in page.items] == [3, 4, 5, 6]


async def test_query_descending(docstore: Any) -> None:
    await docstore.batch_put(
        [DocItem(pk="RUN#r1", sk=f"EVT#{i:012d}", body={"i": i}) for i in range(1, 6)]
    )
    page = await docstore.query(pk="RUN#r1", sk_prefix="EVT#", limit=2, ascending=False)
    assert [i.body["i"] for i in page.items] == [5, 4]


async def test_query_paginates_without_gaps_or_repeats(docstore: Any) -> None:
    await docstore.batch_put(
        [DocItem(pk="RUN#r1", sk=f"EVT#{i:012d}", body={"i": i}) for i in range(1, 26)]
    )

    seen: list[int] = []
    cursor: str | None = None
    for _ in range(10):  # generous bound; the loop should exit well before this
        page = await docstore.query(pk="RUN#r1", sk_prefix="EVT#", limit=7, cursor=cursor)
        seen.extend(i.body["i"] for i in page.items)
        cursor = page.cursor
        if cursor is None:
            break

    assert cursor is None, "pagination did not terminate"
    assert seen == list(range(1, 26))


async def test_query_on_gsi1(docstore: Any) -> None:
    """A5 -- employees on a team."""
    await docstore.batch_put(
        [
            DocItem(
                pk="RUN#r1",
                sk="EMP#emp_017",
                gsi1pk="RUN#r1#TEAM#platform",
                gsi1sk="EMP#emp_017",
                body={"name": "Nikhil"},
            ),
            DocItem(
                pk="RUN#r1",
                sk="EMP#emp_007",
                gsi1pk="RUN#r1#TEAM#payments",
                gsi1sk="EMP#emp_007",
                body={"name": "Priya"},
            ),
        ]
    )
    page = await docstore.query(pk="RUN#r1#TEAM#platform", index="gsi1")
    assert [i.body["name"] for i in page.items] == ["Nikhil"]


async def test_query_on_gsi2(docstore: Any) -> None:
    """A12 -- events for one employee."""
    await docstore.batch_put(
        [
            DocItem(
                pk="RUN#r1",
                sk=f"EVT#{i:012d}",
                gsi2pk="RUN#r1#EMP#emp_017#EVT",
                gsi2sk=f"{i:012d}",
                body={"i": i},
            )
            for i in range(1, 4)
        ]
    )
    page = await docstore.query(pk="RUN#r1#EMP#emp_017#EVT", index="gsi2", ascending=False)
    assert [i.body["i"] for i in page.items] == [3, 2, 1]


async def test_items_without_index_keys_are_absent_from_that_index(docstore: Any) -> None:
    """DynamoDB omits items missing a GSI key; SQLite must agree."""
    await docstore.put(DocItem(pk="RUN#r1", sk="EMP#emp_001", body={}))
    page = await docstore.query(pk="RUN#r1#TEAM#platform", index="gsi1")
    assert page.count == 0


async def test_update_add_creates_and_increments(docstore: Any) -> None:
    """The counter path -- `docs/05-BACKEND-SCHEMA.md` section 4.

    Aggregates are maintained on write, never computed by scanning, so this
    operation runs on every gate decision in the product.
    """
    key = {"pk": "RUN#r1", "sk": "CTR#emp#emp_013#2026-09-18"}

    await docstore.update(**key, patch={"$add": {"requests": 1, "cost_usd": 0.014}})
    await docstore.update(**key, patch={"$add": {"requests": 2, "cost_usd": 0.006}})
    result = await docstore.update(**key, patch={"$add": {"blocked": 1}})

    assert result.body["requests"] == 3
    assert result.body["blocked"] == 1
    assert result.body["cost_usd"] == pytest.approx(0.02)


async def test_update_add_preserves_integers(docstore: Any) -> None:
    """A request count of 3 must not surface as 3.0 -- it crosses into the UI."""
    result = await docstore.update(
        pk="RUN#r1", sk="CTR#run#2026-09-18", patch={"$add": {"requests": 3}}
    )
    assert isinstance(result.body["requests"], int)


async def test_update_sets_plain_fields(docstore: Any) -> None:
    await docstore.put(DocItem(pk="TASK#t1", sk="META", body={"status": "queued"}))
    result = await docstore.update(pk="TASK#t1", sk="META", patch={"status": "working"})
    assert result.body["status"] == "working"


async def test_update_merges_rather_than_replaces(docstore: Any) -> None:
    await docstore.put(DocItem(pk="TASK#t1", sk="META", body={"status": "queued", "repo": "x"}))
    result = await docstore.update(pk="TASK#t1", sk="META", patch={"status": "working"})
    assert result.body == {"status": "working", "repo": "x"}


async def test_update_with_condition_rejects_missing_item(docstore: Any) -> None:
    with pytest.raises(KeyError):
        await docstore.update(
            pk="TASK#ghost",
            sk="META",
            patch={"status": "working"},
            condition="attribute_exists",
        )


async def test_delete(docstore: Any) -> None:
    await docstore.put(DocItem(pk="RUN#r1", sk="EMP#emp_001", body={}))
    await docstore.delete("RUN#r1", "EMP#emp_001")
    assert await docstore.get("RUN#r1", "EMP#emp_001") is None


async def test_floats_survive_the_round_trip(docstore: Any) -> None:
    """DynamoDB numbers are decimal; the adapter converts both ways."""
    await docstore.put(DocItem(pk="TASK#t1", sk="META", body={"cost_usd": 0.0031, "tokens": 1204}))
    fetched = await docstore.get("TASK#t1", "META")
    assert fetched is not None
    assert fetched.body["cost_usd"] == pytest.approx(0.0031)
    assert fetched.body["tokens"] == 1204
    assert isinstance(fetched.body["tokens"], int)


async def test_nested_structures_survive_the_round_trip(docstore: Any) -> None:
    """Decision events store a full context snapshot for replay (decision D8)."""
    snapshot = {
        "actor": {"role": "engineering_intern", "risk_score": 61},
        "matched_policies": [{"policy_id": "pol_block_secret_read", "version": 1}],
        "findings": [],
        "est_cost_usd": 0.0031,
    }
    await docstore.put(DocItem(pk="TASK#t1", sk="REQ#r1", body=snapshot))
    fetched = await docstore.get("TASK#t1", "REQ#r1")
    assert fetched is not None and fetched.body == snapshot


async def test_query_rejects_both_key_conditions(docstore: Any) -> None:
    with pytest.raises(ValueError):
        await docstore.query(pk="RUN#r1", sk_prefix="EVT#", sk_between=("a", "b"))


async def test_query_rejects_unknown_index(docstore: Any) -> None:
    with pytest.raises(ValueError):
        await docstore.query(pk="RUN#r1", index="gsi9")  # type: ignore[arg-type]
