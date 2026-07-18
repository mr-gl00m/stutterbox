from __future__ import annotations

from pathlib import Path

import numpy as np

from conftest import low_motion_frames, record_frames
from core.container import RecordingReader
from core.hashchain import GENESIS_PREV_HASH

WIDTH, HEIGHT = 240, 160


def test_capture_to_reopen_to_reconstruct(tmp_path: Path) -> None:
    """End-to-end: capture a session, reopen it, reconstruct every event."""
    frames = low_motion_frames(WIDTH, HEIGHT, 24)
    path, stats = record_frames(tmp_path, frames, width=WIDTH, height=HEIGHT)
    assert stats.event_count == 24

    with RecordingReader(path, verify=True) as reader:
        assert reader.meta.width == WIDTH
        assert reader.meta.height == HEIGHT
        assert len(reader.events) == 24
        # Every event reconstructs without error, and endpoints are exact.
        for index in range(len(reader.events)):
            frame = reader.reconstruct(index)
            assert frame.shape == (HEIGHT, WIDTH, 3)
        assert np.array_equal(reader.reconstruct(0), frames[0])
        assert np.array_equal(reader.reconstruct(23), frames[-1])


def test_audit_chain_continuity(tmp_path: Path) -> None:
    """The prev_hash chain links genesis -> ... -> last with no gaps."""
    frames = low_motion_frames(WIDTH, HEIGHT, 16)
    path, _ = record_frames(tmp_path, frames, width=WIDTH, height=HEIGHT)
    with RecordingReader(path, verify=True) as reader:
        index = reader.index
        assert index[0].prev_hash == GENESIS_PREV_HASH
        for prev, current in zip(index, index[1:]):
            assert current.prev_hash == prev.frame_sha256
