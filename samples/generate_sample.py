from __future__ import annotations

"""Generate the committed demo recording deterministically.

This simulates a three-minute low-motion "editor" session: a mostly static
screen with a blinking cursor, sparse typing, and occasional scrolls. It is
synthetic on purpose — a shippable sample must not contain real screen pixels,
which Stutterbox treats as sensitive. Re-run to reproduce byte-for-byte.

    uv run python samples/generate_sample.py
"""

import threading
from pathlib import Path

import numpy as np

from core.player import Player
from core.recorder import Recorder, RecorderConfig
from core.model import Frame

WIDTH, HEIGHT = 1280, 720
TICKS = 720  # 3 minutes at 250 ms
INTERVAL_MS = 250
SEED = 20260602

SAMPLE_PATH = Path(__file__).resolve().parent / "sample_coding_session.stut"


def _base_frame() -> Frame:
    frame = np.empty((HEIGHT, WIDTH, 3), dtype=np.uint8)
    frame[:, :] = (24, 24, 28)  # editor background
    # A gutter and a status bar so the keyframe is structured, not flat.
    frame[:, 0:48] = (32, 32, 38)
    frame[HEIGHT - 24 :, :] = (40, 70, 110)
    # Static "code" lines.
    for row in range(40, HEIGHT - 60, 22):
        length = 120 + (row * 37) % 700
        frame[row : row + 12, 64 : 64 + length] = (70, 74, 82)
    return frame


class Session:
    """A deterministic grab source: one mutated copy per tick, then None."""

    def __init__(self) -> None:
        self._rng = np.random.default_rng(SEED)
        self._canvas = _base_frame()
        self._tick = 0
        self._caret_row = 40
        self._caret_col = 64

    @property
    def grabs(self) -> int:
        """Completed grab() calls so far == the current tick cursor."""
        return self._tick

    def __call__(self) -> Frame | None:
        if self._tick > TICKS:
            return None
        if self._tick == 0:
            self._tick += 1
            first: Frame = self._canvas.copy()
            return first

        nxt: Frame = self._canvas.copy()
        self._advance(nxt)
        self._canvas = nxt
        self._tick += 1
        return nxt

    def _advance(self, frame: Frame) -> None:
        tick = self._tick

        # Blinking caret every other tick (tiny change).
        caret_on = (tick // 2) % 2 == 0
        color = (220, 220, 220) if caret_on else (24, 24, 28)
        frame[self._caret_row : self._caret_row + 12,
              self._caret_col : self._caret_col + 3] = color

        # Sparse typing: ~35% of ticks add a glyph and move the caret.
        if self._rng.random() < 0.35:
            glyph = int(self._rng.integers(90, 200))
            frame[self._caret_row : self._caret_row + 12,
                  self._caret_col : self._caret_col + 8] = (glyph, glyph, glyph + 20 & 255)
            self._caret_col += 10
            if self._caret_col > WIDTH - 80:
                self._caret_col = 64
                self._caret_row += 22
                if self._caret_row > HEIGHT - 80:
                    self._caret_row = 40

        # Occasional scroll: shift the code band up by one line.
        if tick % 47 == 0:
            band = frame[40 : HEIGHT - 60].copy()
            frame[40 : HEIGHT - 82] = band[22:]

        # Rare view switch: repaint a large pane.
        if tick % 211 == 0:
            tint = int(self._rng.integers(20, 36))
            frame[40 : HEIGHT - 60, 48:] = (tint, tint, tint + 4)


def main() -> None:
    session = Session()
    temp_path = SAMPLE_PATH.with_suffix(".stut.tmp")

    # Simulated monotonic clock keyed to the grab count, so tick i lands on an
    # exact i*250 ms boundary no matter how many times the recorder samples the
    # clock per tick. The first grab is the keyframe (stored at ts 0), so floor
    # the count at one before scaling; the pre-grab `start` read then reads 0.
    # Keying on grabs (not a fixed call budget) keeps this robust to the
    # recorder's pacing: 722c127 made it sample the clock three times per tick
    # instead of once, which exhausted the old range(TICKS+5) counter.
    def mono_clock() -> float:
        return max(session.grabs - 1, 0) * (INTERVAL_MS / 1000.0)

    recorder = Recorder(
        temp_path=temp_path,
        final_path=SAMPLE_PATH,
        geometry=(WIDTH, HEIGHT),
        grab=session,
        config=RecorderConfig(interval_ms=0, diff_threshold=12, tile_size=48),
        monitor=1,
        overwrite=True,
        mono_clock=mono_clock,
        wall_clock=lambda: 1_780_000_000.0,
    )
    stats = recorder.run(threading.Event())

    raw_bytes = TICKS * WIDTH * HEIGHT * 3
    file_bytes = SAMPLE_PATH.stat().st_size
    with Player(SAMPLE_PATH, verify=True) as player:
        events = player.event_count
        player.seek(events - 1)

    print(f"sample written  : {SAMPLE_PATH.name}")
    print(f"resolution      : {WIDTH}x{HEIGHT}")
    print(f"ticks           : {TICKS} ({TICKS * INTERVAL_MS // 1000}s at {INTERVAL_MS}ms)")
    print(f"change_events   : {stats.event_count}")
    print(f"frames_stored   : {stats.frame_count}")
    print(f"file_bytes      : {file_bytes}")
    print(f"raw_equiv_bytes : {raw_bytes}")
    print(f"ratio_pct       : {100.0 * file_bytes / raw_bytes:.4f}")
    print(f"reopen_events   : {events}")


if __name__ == "__main__":
    main()
