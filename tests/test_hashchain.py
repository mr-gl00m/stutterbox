from __future__ import annotations

from core.hashchain import GENESIS_PREV_HASH, frame_digest
from core.model import Region


def test_digest_is_deterministic() -> None:
    region = Region(0, 0, 10, 10)
    a = frame_digest(GENESIS_PREV_HASH, 0, "keyframe", region, b"abc")
    b = frame_digest(GENESIS_PREV_HASH, 0, "keyframe", region, b"abc")
    assert a == b
    assert len(a) == 64


def test_digest_changes_with_blob() -> None:
    region = Region(0, 0, 10, 10)
    a = frame_digest(GENESIS_PREV_HASH, 0, "keyframe", region, b"abc")
    b = frame_digest(GENESIS_PREV_HASH, 0, "keyframe", region, b"abd")
    assert a != b


def test_digest_changes_with_prev_hash() -> None:
    region = Region(0, 0, 10, 10)
    a = frame_digest(GENESIS_PREV_HASH, 5, "delta", region, b"x")
    b = frame_digest("1" * 64, 5, "delta", region, b"x")
    assert a != b


def test_digest_changes_with_region() -> None:
    a = frame_digest(GENESIS_PREV_HASH, 0, "delta", Region(0, 0, 10, 10), b"x")
    b = frame_digest(GENESIS_PREV_HASH, 0, "delta", Region(1, 0, 10, 10), b"x")
    assert a != b
