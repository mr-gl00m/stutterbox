from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import pytest

from core.model import Frame
from core.recorder import Recorder, RecorderConfig

WIDTH, HEIGHT = 64, 48
INTERVAL_S = 0.25
PROCESS_S = 0.10


class _PacingStop(threading.Event):
    """Models a perfect sleeper plus a fixed per-tick processing cost.

    ``wait`` advances virtual time by the requested delay (the sleep), and each
    grab advances it by the processing budget. The delays the recorder asks for
    then reveal whether it paces on a fixed schedule or lets work accumulate.
    """

    def __init__(self, interval_s: float, process_s: float) -> None:
        super().__init__()
        self.now = 0.0
        self._interval = interval_s
        self._process = process_s
        self.requested: list[float] = []

    def mono(self) -> float:
        return self.now

    def on_grab(self) -> None:
        self.now += self._process

    def wait(self, timeout: float | None = None) -> bool:
        self.requested.append(timeout if timeout is not None else 0.0)
        if timeout and timeout > 0:
            self.now += timeout
        return False


def test_capture_paces_on_a_fixed_schedule(tmp_path: Path) -> None:
    stop = _PacingStop(INTERVAL_S, PROCESS_S)
    base = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    state = {"i": 0}

    def grab() -> Frame | None:
        i = state["i"]
        state["i"] += 1
        stop.on_grab()  # this tick's processing cost
        if i >= 6:
            return None
        frame: Frame = base.copy()
        frame[0:16, 0:16] = np.uint8((i * 40) % 256)  # change every tick
        return frame

    recorder = Recorder(
        temp_path=tmp_path / ".p.tmp",
        final_path=tmp_path / "p.stut",
        geometry=(WIDTH, HEIGHT),
        grab=grab,
        config=RecorderConfig(
            interval_ms=int(INTERVAL_S * 1000), diff_threshold=12, tile_size=16
        ),
        mono_clock=stop.mono,
        wall_clock=lambda: 1_700_000_000.0,
    )
    recorder.run(stop)

    assert len(stop.requested) >= 4
    # Each wait compensates for processing time, so it is interval - process,
    # not the full interval, and it does not drift across ticks.
    for delay in stop.requested:
        assert delay == pytest.approx(INTERVAL_S - PROCESS_S, abs=1e-9)
    assert max(stop.requested) - min(stop.requested) < 1e-9
