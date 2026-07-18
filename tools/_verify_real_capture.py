from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

from core.capture import ScreenCapturer
from core.player import Player
from core.recorder import Recorder, RecorderConfig

DURATION_S = 130
INTERVAL_MS = 250


def main() -> None:
    out_dir = Path(tempfile.gettempdir()) / "stutterbox_real_verify"
    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / "real.stut"
    temp = out_dir / ".real.stut.tmp"

    capturer = ScreenCapturer(1)
    capturer.start()
    width, height = capturer.geometry

    recorder = Recorder(
        temp_path=temp,
        final_path=final,
        geometry=(width, height),
        grab=lambda: capturer.grab(),
        config=RecorderConfig(interval_ms=INTERVAL_MS, diff_threshold=12, tile_size=48),
        monitor=1,
        overwrite=True,
    )
    stop = threading.Event()
    timer = threading.Timer(DURATION_S, stop.set)
    timer.start()

    started = time.monotonic()
    stats = recorder.run(stop)
    elapsed = time.monotonic() - started
    capturer.close()

    ticks = max(1, int(elapsed / (INTERVAL_MS / 1000.0)))
    raw_bytes = ticks * width * height * 3
    file_bytes = final.stat().st_size

    # Prove it reopens and reconstructs.
    with Player(final, verify=True) as player:
        first = player.seek(0)
        last = player.seek(player.event_count - 1)
        ok_shape = first.shape == (height, width, 3) == last.shape

    print("=== REAL CAPTURE VERIFICATION ===")
    print(f"resolution      : {width}x{height}")
    print(f"elapsed_s       : {elapsed:.1f}")
    print(f"approx_ticks    : {ticks}")
    print(f"change_events   : {stats.event_count}")
    print(f"frames_stored   : {stats.frame_count}")
    print(f"file_bytes      : {file_bytes}")
    print(f"raw_equiv_bytes : {raw_bytes}")
    print(f"ratio_pct       : {100.0 * file_bytes / raw_bytes:.3f}")
    print(f"reopen_verified : {ok_shape}")
    print(f"path            : {final}")


if __name__ == "__main__":
    main()
