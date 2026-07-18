from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

from core.model import Frame
from core.recorder import Recorder, RecorderConfig, RecordingStats


def gradient_base(width: int, height: int) -> Frame:
    """A static, non-trivial base frame so the keyframe is not all one color."""
    base = np.zeros((height, width, 3), dtype=np.uint8)
    ramp = np.linspace(0, 255, width, dtype=np.uint8)
    base[:, :, 0] = ramp[None, :]
    base[:, :, 1] = ramp[None, :] // 2
    return base


def low_motion_frames(width: int, height: int, count: int) -> list[Frame]:
    """A low-motion sequence: each frame adds one small block to the prior one."""
    frames: list[Frame] = [gradient_base(width, height)]
    block = 20
    for i in range(1, count):
        frame = frames[-1].copy()
        x = (i * 17) % (width - block)
        y = (i * 13) % (height - block)
        frame[y : y + block, x : x + block] = np.uint8((i * 37) % 256)
        frames.append(frame)
    return frames


def record_frames(
    tmp_path: Path,
    frames: list[Frame],
    *,
    width: int,
    height: int,
    threshold: int = 12,
    tile: int = 16,
    name: str = "rec.stut",
) -> tuple[Path, RecordingStats]:
    """Record a fixed frame list into a finalized .stut with deterministic time."""
    final_path = tmp_path / name
    temp_path = tmp_path / f".{name}.tmp"
    iterator = iter(frames)

    def grab() -> Frame | None:
        return next(iterator, None)

    counter = iter(range(1_000_000))

    def mono() -> float:
        return next(counter) * 0.1

    recorder = Recorder(
        temp_path=temp_path,
        final_path=final_path,
        geometry=(width, height),
        grab=grab,
        config=RecorderConfig(interval_ms=0, diff_threshold=threshold, tile_size=tile),
        mono_clock=mono,
        wall_clock=lambda: 1_700_000_000.0,
    )
    stats = recorder.run(threading.Event())
    return final_path, stats
