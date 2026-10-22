"""Shared small utilities."""

from __future__ import annotations

import asyncio
import random


async def polite_delay(min_s: float = 8.0, max_s: float = 15.0) -> None:
    """Random sleep between min and max seconds."""
    delay = random.uniform(min_s, max_s)
    delay = max(3.0, delay)
    await asyncio.sleep(delay)


async def short_pause(min_ms: int = 200, max_ms: int = 600) -> None:
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000.0)
