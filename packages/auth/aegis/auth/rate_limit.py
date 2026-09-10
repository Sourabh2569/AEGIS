from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class LoginRateLimiter:
    """Real per-username sliding-window limiter for POST /api/v1/auth/login.

    Keyed by username, not caller IP: this app has a small, fixed set of
    real accounts, and IP-based limiting alone would let a shared/proxied
    IP mask an attack on one specific account, or let an attacker just
    rotate source IPs. Username-keying directly protects the actual asset.

    A sliding window rather than a separate "locked" flag -- failures older
    than `window` simply age out on the next check, so there's no separate
    unlock bookkeeping to get wrong.
    """

    max_attempts: int = 5
    window: timedelta = timedelta(minutes=15)
    _failures_by_username: dict[str, list[datetime]] = field(default_factory=dict)

    def seconds_until_allowed(self, username: str, now: datetime) -> int:
        """0 if this username may attempt login right now; otherwise the
        real number of seconds until the oldest counted failure ages out of
        the window."""
        window_start = now - self.window
        recent = [
            failed_at
            for failed_at in self._failures_by_username.get(username, [])
            if failed_at >= window_start
        ]
        self._failures_by_username[username] = recent
        if len(recent) < self.max_attempts:
            return 0
        oldest = min(recent)
        return max(1, int((oldest + self.window - now).total_seconds()))

    def record_failure(self, username: str, now: datetime) -> None:
        self._failures_by_username.setdefault(username, []).append(now)

    def record_success(self, username: str) -> None:
        self._failures_by_username.pop(username, None)
