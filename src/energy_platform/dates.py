"""Date helpers."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def chunk_range(start: date, end: date, days: int) -> Iterator[tuple[date, date]]:
    """Split [start, end] (inclusive) into consecutive chunks of at most `days` days."""
    if end < start:
        raise ValueError(f"end {end} is before start {start}")
    if days < 1:
        raise ValueError("days must be >= 1")
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=days - 1), end)
        yield cur, chunk_end
        cur = chunk_end + timedelta(days=1)
