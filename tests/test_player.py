from __future__ import annotations

from pathlib import Path

import numpy as np

from conftest import low_motion_frames, record_frames
from core.player import Player

WIDTH, HEIGHT = 160, 120


def _record(tmp_path: Path, count: int = 10) -> Path:
    frames = low_motion_frames(WIDTH, HEIGHT, count)
    path, _ = record_frames(tmp_path, frames, width=WIDTH, height=HEIGHT)
    return path


def test_player_opens_and_counts_events(tmp_path: Path) -> None:
    with Player(_record(tmp_path, 10)) as player:
        assert player.event_count == 10
        assert player.current_index == 0


def test_next_and_prev_change(tmp_path: Path) -> None:
    with Player(_record(tmp_path, 6)) as player:
        assert player.has_next()
        assert not player.has_prev()
        player.next_change()
        assert player.current_index == 1
        assert player.has_prev()
        player.prev_change()
        assert player.current_index == 0


def test_seek_clamps(tmp_path: Path) -> None:
    with Player(_record(tmp_path, 5)) as player:
        player.seek(100)
        assert player.current_index == player.event_count - 1
        player.seek(-5)
        assert player.current_index == 0


def test_seek_returns_correct_frame(tmp_path: Path) -> None:
    frames = low_motion_frames(WIDTH, HEIGHT, 8)
    path, _ = record_frames(tmp_path, frames, width=WIDTH, height=HEIGHT)
    with Player(path) as player:
        first = player.seek(0)
        assert np.array_equal(first, frames[0])
        last = player.seek(player.event_count - 1)
        assert np.array_equal(last, frames[-1])
