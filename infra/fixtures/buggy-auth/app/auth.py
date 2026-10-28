"""Session-token store for the Acme internal dashboard.

A session is created by `login` and must be rejected once its time-to-live
has elapsed. Tokens are opaque strings; expiry is compared against the
monotonic seconds supplied by the caller.
"""

from __future__ import annotations

TTL_SECONDS = 3600


class SessionStore:
    """In-memory session registry keyed by opaque token."""

    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, object]] = {}

    def login(self, user: str, now: int) -> str:
        """Issue a token for `user`, valid for TTL_SECONDS."""
        token = f"tok-{user}-{now}"
        self.sessions[token] = {"user": user, "expires_at": now + TTL_SECONDS}
        return token

    def verify_token(self, token: str, now: int) -> bool:
        """Return True only while the session is unexpired."""
        session = self.sessions.get(token)
        if session is None:
            return False
        expires_at = int(session["expires_at"])  # type: ignore[call-arg]
        return now >= expires_at
