from __future__ import annotations

import hashlib

from core.model import FrameKind, Region

# The chain anchor for the first frame in a recording.
GENESIS_PREV_HASH: str = "0" * 64


def frame_digest(
    prev_hash: str,
    ts_ms: int,
    kind: FrameKind,
    region: Region,
    blob: bytes,
) -> str:
    """Compute the hash-linked digest for one frame row.

    The previous frame's digest is folded in, so editing any earlier frame's
    pixels invalidates every digest after it — the recording is tamper-evident
    without a separate audit log.
    """
    hasher = hashlib.sha256()
    hasher.update(bytes.fromhex(prev_hash))
    kind_bytes = kind.encode("ascii")
    hasher.update(len(kind_bytes).to_bytes(2, "big"))
    hasher.update(kind_bytes)
    hasher.update(ts_ms.to_bytes(8, "big", signed=False))
    for value in (region.x, region.y, region.w, region.h):
        hasher.update(value.to_bytes(4, "big", signed=False))
    hasher.update(len(blob).to_bytes(8, "big"))
    hasher.update(blob)
    return hasher.hexdigest()
