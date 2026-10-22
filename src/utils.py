"""Small helpers."""

from __future__ import annotations

import asyncio
import random
from typing import Any


async def polite_delay(base_sec: float, jitter: float = 0.4) -> None:
    """Sleep base_sec +/- jitter fraction."""
    delay = base_sec * (1.0 + random.uniform(-jitter, jitter))
    delay = max(3.0, delay)
    await asyncio.sleep(delay)
