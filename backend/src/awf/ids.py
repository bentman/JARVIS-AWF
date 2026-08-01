"""UUIDv7 identifiers (RFC 9562), stdlib-only for Python <3.14 where uuid.uuid7 is unavailable."""

import os
import time
import uuid


def uuid7() -> str:
    if hasattr(uuid, "uuid7"):
        return str(uuid.uuid7())

    ts_ms = time.time_ns() // 1_000_000
    ts_bytes = ts_ms.to_bytes(6, "big")
    rand_bytes = bytearray(os.urandom(10))
    rand_bytes[0] = (rand_bytes[0] & 0x0F) | 0x70  # version 7
    rand_bytes[2] = (rand_bytes[2] & 0x3F) | 0x80  # variant 10
    return str(uuid.UUID(bytes=bytes(ts_bytes + rand_bytes)))
