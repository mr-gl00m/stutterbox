from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import NamedTuple

import pytest

from conftest import low_motion_frames, record_frames
from core.errors import CaptureError
from core.model import Frame
from core.recorder import Recorder, RecorderConfig

WIDTH, HEIGHT = 160, 120


class _DiskUsage(NamedTuple):
    total: int
    used: int
    free: int


def test_records_finalized_stut(tmp_path: Path) -> None:
    frames = low_motion_frames(WIDTH, HEIGHT, 12)
    path, stats = record_frames(tmp_path, frames, width=WIDTH, height=HEIGHT)
    assert path.exists()
    assert stats.event_count == 12  # 1 keyframe + 11 changing deltas
    assert stats.frame_count >= stats.event_count
    assert not (tmp_path / ".rec.stut.tmp").exists()


def test_size_win_versus_raw(tmp_path: Path) -> None:
    count = 40
    frames = low_motion_frames(WIDTH, HEIGHT, count)
    path, stats = record_frames(tmp_path, frames, width=WIDTH, height=HEIGHT)
    raw_bytes = count * WIDTH * HEIGHT * 3
    file_bytes = path.stat().st_size
    # Low-motion capture must be dramatically smaller than raw frames.
    assert file_bytes < raw_bytes * 0.25
    ratio = file_bytes / raw_bytes
    assert ratio < 0.25  # documents the win; see report for measured value


def test_crash_leaves_no_final_or_temp(tmp_path: Path) -> None:
    final_path = tmp_path / "rec.stut"
    temp_path = tmp_path / ".rec.stut.tmp"
    frames = low_motion_frames(WIDTH, HEIGHT, 5)
    iterator = iter(frames)
    calls = {"n": 0}

    def grab() -> Frame | None:
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("simulated capture crash")
        return next(iterator, None)

    counter = iter(range(1000))

    recorder = Recorder(
        temp_path=temp_path,
        final_path=final_path,
        geometry=(WIDTH, HEIGHT),
        grab=grab,
        config=RecorderConfig(interval_ms=0, diff_threshold=12, tile_size=16),
        mono_clock=lambda: next(counter) * 0.1,
        wall_clock=lambda: 1_700_000_000.0,
    )
    with pytest.raises(RuntimeError):
        recorder.run(threading.Event())
    assert not final_path.exists()
    assert not temp_path.exists()


def test_no_frames_raises(tmp_path: Path) -> None:
    recorder = Recorder(
        temp_path=tmp_path / ".x.tmp",
        final_path=tmp_path / "x.stut",
        geometry=(WIDTH, HEIGHT),
        grab=lambda: None,
        config=RecorderConfig(interval_ms=0, diff_threshold=12, tile_size=16),
    )
    with pytest.raises(CaptureError):
        recorder.run(threading.Event())


def test_stop_event_ends_loop(tmp_path: Path) -> None:
    base = low_motion_frames(WIDTH, HEIGHT, 1)[0]
    stop = threading.Event()
    grabs = {"n": 0}

    def grab() -> Frame | None:
        grabs["n"] += 1
        if grabs["n"] >= 4:
            stop.set()
        return base  # recorder never mutates the frame, so sharing is safe

    counter = iter(range(1000))
    recorder = Recorder(
        temp_path=tmp_path / ".s.tmp",
        final_path=tmp_path / "s.stut",
        geometry=(WIDTH, HEIGHT),
        grab=grab,
        config=RecorderConfig(interval_ms=0, diff_threshold=12, tile_size=16),
        mono_clock=lambda: next(counter) * 0.1,
        wall_clock=lambda: 1_700_000_000.0,
    )
    stats = recorder.run(stop)
    # A static screen yields just the keyframe event.
    assert stats.event_count == 1
    assert (tmp_path / "s.stut").exists()


def test_existing_final_is_never_replaced(tmp_path: Path) -> None:
    final_path = tmp_path / "existing.stut"
    temp_path = tmp_path / ".existing.stut.tmp"
    original = b"existing recording bytes"
    final_path.write_bytes(original)
    frames = iter(low_motion_frames(WIDTH, HEIGHT, 2))
    counter = iter(range(1000))
    recorder = Recorder(
        temp_path=temp_path,
        final_path=final_path,
        geometry=(WIDTH, HEIGHT),
        grab=lambda: next(frames, None),
        config=RecorderConfig(interval_ms=0, diff_threshold=12, tile_size=16),
        mono_clock=lambda: next(counter) * 0.1,
        wall_clock=lambda: 1_700_000_000.0,
    )

    with pytest.raises(CaptureError, match="already exists"):
        recorder.run(threading.Event())

    assert final_path.read_bytes() == original
    assert not temp_path.exists()


def test_low_disk_floor_finalizes_partial_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def fake_disk_usage(_path: object) -> _DiskUsage:
        nonlocal calls
        calls += 1
        free = 2 * 1024**3 if calls == 1 else 0
        return _DiskUsage(total=4 * 1024**3, used=2 * 1024**3, free=free)

    monkeypatch.setattr(shutil, "disk_usage", fake_disk_usage)
    final_path = tmp_path / "low-disk.stut"
    frames = iter(low_motion_frames(WIDTH, HEIGHT, 4))
    counter = iter(range(1000))
    recorder = Recorder(
        temp_path=tmp_path / ".low-disk.stut.tmp",
        final_path=final_path,
        geometry=(WIDTH, HEIGHT),
        grab=lambda: next(frames, None),
        config=RecorderConfig(interval_ms=0, diff_threshold=12, tile_size=16),
        mono_clock=lambda: next(counter) * 0.1,
        wall_clock=lambda: 1_700_000_000.0,
    )

    stats = recorder.run(threading.Event())

    assert stats.event_count == 1
    assert stats.stopped_for_low_disk
    assert final_path.exists()
