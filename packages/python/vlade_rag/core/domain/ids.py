"""Identifier helpers."""

from __future__ import annotations

import os
import time
import uuid

_RAND_A_MASK = (1 << 12) - 1
_RAND_B_MASK = (1 << 62) - 1
_TS_MASK = (1 << 48) - 1


def uuid7() -> uuid.UUID:
    """Return a UUID version 7 (RFC 9562): time-ordered, better index locality than UUID4."""
    unix_ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    value = (unix_ms & _TS_MASK) << 80
    value |= 0x7 << 76
    value |= ((rand >> 62) & _RAND_A_MASK) << 64
    value |= 0b10 << 62
    value |= rand & _RAND_B_MASK
    return uuid.UUID(int=value)
