from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

from conftest import gradient_base
from core.capture import ScreenCapturer
from core.container import RecordingReader
from core.model import Frame, Region
from core.recorder import Recorder, RecorderConfig

WIDTH, HEIGHT = 160, 120
EXCLUDE = Region(0, 0, 48, 48)


def test_blank_regions_zeros_only_the_region() -> None:
    frame = np.full((HEIGHT, WIDTH, 3), 200, dtype=np.uint8)
    ScreenCapturer.blank_regions(frame, [EXCLUDE])
    assert np.all(frame[0:48, 0:48] == 0)
    # Everything outside the region is untouched.
    assert np.all(frame[48:, :] == 200)
    assert np.all(frame[:, 48:] == 200)


def test_blank_regions_clamps_out_of_bounds() -> None:
    frame = np.full((HEIGHT, WIDTH, 3), 200, dtype=np.uint8)
    ScreenCapturer.blank_regions(frame, [Region(140, 100, 999, 999)])
    assert np.all(frame[100:, 140:] == 0)
    assert np.all(frame[0:100, 0:140] == 200)


def _frames_changing_inside_and_outside(count: int) -> list[Frame]:
    """Frames that change every tick both inside and outside the exclude box."""
    frames = [gradient_base(WIDTH, HEIGHT)]
    for i in range(1, count):
        frame = frames[-1].copy()
        # Always change inside the exclude region...
        frame[8:24, 8:24] = np.uint8((i * 53) % 256)
        # ...and somewhere well outside it.
        frame[80:96, 100:120] = np.uint8((i * 31) % 256)
        frames.append(frame)
    return frames


def test_excluded_region_is_never_captured(tmp_path: Path) -> None:
    frames = _frames_changing_inside_and_outside(12)
    iterator = iter(frames)

    def grab() -> Frame | None:
        frame = next(iterator, None)
        if frame is None:
            return None
        masked: Frame = frame.copy()
        ScreenCapturer.blank_regions(masked, [EXCLUDE])
        return masked

    counter = iter(range(1000))
    recorder = Recorder(
        temp_path=tmp_path / ".x.tmp",
        final_path=tmp_path / "x.stut",
        geometry=(WIDTH, HEIGHT),
        grab=grab,
        config=RecorderConfig(interval_ms=0, diff_threshold=12, tile_size=16),
        mono_clock=lambda: next(counter) * 0.1,
        wall_clock=lambda: 1_700_000_000.0,
    )
    stats = recorder.run(threading.Event())

    # The out-of-box change is still recorded, so capture is alive.
    assert stats.event_count > 1
    with RecordingReader(tmp_path / "x.stut", verify=True) as reader:
        for index in range(len(reader.events)):
            frame = reader.reconstruct(index)
            assert np.all(frame[0:48, 0:48] == 0), f"exclude leaked at event {index}"
