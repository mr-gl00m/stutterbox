from __future__ import annotations

import os
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from core.codec import encode_region
from core.config import APP_VERSION
from core.container import SCHEMA_VERSION, RecordingWriter
from core.diff import changed_regions
from core.errors import CaptureError
from core.io import atomic_publish_file
from core.model import Frame, RecordingMeta, Region

# A grab returns the next frame, or None to end the stream cleanly.
GrabFn = Callable[[], Frame | None]
# Called once per recorded event with (ts_ms, region_count).
EventCallback = Callable[[int, int], None]

# Keep enough space for one worst-case display frame plus SQLite finalization.
MIN_FREE_DISK_BYTES: int = 1024**3


@dataclass(frozen=True)
class RecorderConfig:
    interval_ms: int
    diff_threshold: int
    tile_size: int


@dataclass(frozen=True)
class RecordingStats:
    path: Path
    duration_ms: int
    event_count: int
    frame_count: int
    blob_bytes: int
    width: int
    height: int
    stopped_for_low_disk: bool


class Recorder:
    """Drives capture -> diff -> container, finalizing atomically on stop.

    The loop writes to ``temp_path`` and publishes it only after a clean stop,
    so a crash never leaves a half-written recording presented as complete.
    """

    def __init__(
        self,
        *,
        temp_path: Path,
        final_path: Path,
        geometry: tuple[int, int],
        grab: GrabFn,
        config: RecorderConfig,
        monitor: int = 1,
        capture_format: str = "png",
        overwrite: bool = False,
        mono_clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self._temp_path = Path(temp_path)
        self._final_path = Path(final_path)
        self._width, self._height = geometry
        self._grab = grab
        self._config = config
        self._monitor = monitor
        self._capture_format = capture_format
        self._overwrite = overwrite
        self._mono_clock = mono_clock
        self._wall_clock = wall_clock

    def run(
        self, stop: threading.Event, on_event: EventCallback | None = None
    ) -> RecordingStats:
        self._final_path.parent.mkdir(parents=True, exist_ok=True)
        self._temp_path.parent.mkdir(parents=True, exist_ok=True)
        if self._disk_space_low():
            raise CaptureError("recordings volume has less than 1 GiB free")
        if not self._overwrite and self._final_path.exists():
            raise CaptureError(f"recording already exists: {self._final_path}")
        try:
            fd = os.open(
                self._temp_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
            os.close(fd)
        except FileExistsError as exc:
            raise CaptureError(
                f"temporary recording already exists: {self._temp_path}"
            ) from exc
        except OSError as exc:
            raise CaptureError(
                f"could not reserve temporary recording {self._temp_path}: {exc}"
            ) from exc

        try:
            writer = RecordingWriter(self._temp_path)
        except BaseException:
            self._temp_path.unlink(missing_ok=True)
            raise
        interval_s = self._config.interval_ms / 1000.0
        try:
            writer.write_meta(self._build_meta())
            start = self._mono_clock()

            first = self._grab()
            if first is None:
                raise CaptureError("no frames captured; nothing to record")
            self._check_shape(first)
            writer.append_frame(
                0, "keyframe", Region(0, 0, self._width, self._height),
                encode_region(first),
            )
            if on_event is not None:
                on_event(0, 1)

            prev = first
            event_count = 1
            last_ts = 0
            stopped_for_low_disk = False
            # Pace on a fixed schedule (start + k*interval) rather than waiting
            # a full interval after each tick's processing. Without this, the
            # grab + diff + encode time is added on top of the interval and the
            # real cadence drifts well past the configured value.
            next_due = start
            while True:
                next_due += interval_s
                delay = next_due - self._mono_clock()
                if delay > 0:
                    if stop.wait(delay):
                        break
                else:
                    if stop.is_set():
                        break
                    # Behind schedule: drop the backlog so we don't burst-grab.
                    next_due = self._mono_clock()
                if self._disk_space_low():
                    stopped_for_low_disk = True
                    break
                curr = self._grab()
                if curr is None:
                    break
                self._check_shape(curr)
                ts_ms = int((self._mono_clock() - start) * 1000)
                regions = changed_regions(
                    prev,
                    curr,
                    threshold=self._config.diff_threshold,
                    tile=self._config.tile_size,
                )
                if regions:
                    self._write_regions(writer, ts_ms, curr, regions)
                    event_count += 1
                    last_ts = ts_ms
                    if on_event is not None:
                        on_event(ts_ms, len(regions))
                prev = curr

            stats = writer.finalize()
            try:
                atomic_publish_file(
                    self._temp_path,
                    self._final_path,
                    overwrite=self._overwrite,
                )
            except FileExistsError as exc:
                raise CaptureError(f"recording already exists: {self._final_path}") from exc
            except OSError as exc:
                raise CaptureError(f"could not publish recording: {exc}") from exc
        except BaseException:
            writer.close()
            Path(self._temp_path).unlink(missing_ok=True)
            raise

        return RecordingStats(
            path=self._final_path,
            duration_ms=last_ts,
            event_count=event_count,
            frame_count=stats.frame_count,
            blob_bytes=stats.blob_bytes,
            width=self._width,
            height=self._height,
            stopped_for_low_disk=stopped_for_low_disk,
        )

    def _disk_space_low(self) -> bool:
        try:
            free = shutil.disk_usage(self._temp_path.parent).free
        except OSError as exc:
            raise CaptureError(f"could not read recordings volume space: {exc}") from exc
        return free < MIN_FREE_DISK_BYTES

    def _write_regions(
        self, writer: RecordingWriter, ts_ms: int, frame: Frame, regions: list[Region]
    ) -> None:
        for region in regions:
            patch = np.ascontiguousarray(
                frame[region.y : region.y + region.h, region.x : region.x + region.w]
            )
            writer.append_frame(ts_ms, "delta", region, encode_region(patch))

    def _build_meta(self) -> RecordingMeta:
        return RecordingMeta(
            schema_version=SCHEMA_VERSION,
            app_version=APP_VERSION,
            created_ms=int(self._wall_clock() * 1000),
            width=self._width,
            height=self._height,
            monitor=self._monitor,
            interval_ms=self._config.interval_ms,
            diff_threshold=self._config.diff_threshold,
            tile_size=self._config.tile_size,
            capture_format=self._capture_format,
        )

    def _check_shape(self, frame: Frame) -> None:
        if frame.shape != (self._height, self._width, 3):
            raise CaptureError(
                f"frame shape {frame.shape!r} does not match geometry "
                f"({self._height}, {self._width}, 3)"
            )
