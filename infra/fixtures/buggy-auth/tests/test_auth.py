"""Tests for the session-token store.

The suite currently FAILS: expired sessions are accepted. This is the
fixture the Autopilot demo runs against.
"""

from __future__ import annotations

import pytest

from app.auth import TTL_SECONDS, SessionStore


def test_fresh_token_is_accepted() -> None:
    store = SessionStore()
    token = store.login("alice", now=1_000)
    assert store.verify_token(token, now=1_005) is True


def test_expired_token_is_rejected() -> None:
    store = SessionStore()
    token = store.login("alice", now=1_000)
    assert store.verify_token(token, now=1_000 + TTL_SECONDS + 1) is False


def test_token_at_exact_expiry_is_rejected() -> None:
    store = SessionStore()
    token = store.login("alice", now=1_000)
    assert store.verify_token(token, now=1_000 + TTL_SECONDS) is False


def test_unknown_token_is_rejected() -> None:
    store = SessionStore()
    assert store.verify_token("tok-nobody-0", now=1) is False


def test_login_issues_a_distinct_token_per_user() -> None:
    store = SessionStore()
    alice = store.login("alice", now=1)
    bob = store.login("bob", now=1)
    assert alice != bob


@pytest.mark.parametrize(
    "user", ["alice", "bob", "carol"], ids=["alice", "bob", "carol"]
)
def test_tokens_expire_independently(user: str) -> None:
    store = SessionStore()
    token = store.login(user, now=10)
    assert store.verify_token(token, now=11) is True
