"""
In-memory rate limiter for the live demo (SPEC.md §11).

Two caps:
- Per-IP sliding window: 20 prompts / 24h
- Global daily $ ceiling: ~$10/day (tracked by approximate Haiku token cost;
  swap for real Anthropic cost-header tracking once we have request volume)

Both are intentionally in-memory — a single Railway / Fly dyno is fine for v0.
If the app horizontally scales we swap for Redis or the equivalent.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque

_PROMPTS_PER_IP_PER_DAY = int(os.environ.get("RATE_LIMIT_PER_IP", "20"))
_DAILY_USD_CAP = float(os.environ.get("DAILY_USD_CAP", "10.0"))

_DAY_SECONDS = 24 * 60 * 60

_ip_log: dict[str, deque[float]] = defaultdict(deque)
_spend_log: deque[tuple[float, float]] = deque()


def _trim_old(now: float) -> None:
    cutoff = now - _DAY_SECONDS
    for entries in _ip_log.values():
        while entries and entries[0] < cutoff:
            entries.popleft()
    while _spend_log and _spend_log[0][0] < cutoff:
        _spend_log.popleft()


def check_allowed(ip: str) -> tuple[bool, str | None]:
    now = time.time()
    _trim_old(now)
    if len(_ip_log[ip]) >= _PROMPTS_PER_IP_PER_DAY:
        return False, "rate_limit_per_ip"
    spent_today = sum(amount for _, amount in _spend_log)
    if spent_today >= _DAILY_USD_CAP:
        return False, "rate_limit_daily_budget"
    return True, None


def record_request(ip: str, estimated_usd: float = 0.005) -> None:
    """Call after a request completes. estimated_usd defaults to a typical Haiku cached turn."""
    now = time.time()
    _ip_log[ip].append(now)
    _spend_log.append((now, estimated_usd))
