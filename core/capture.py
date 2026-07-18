from __future__ import annotations

import numpy as np

from core.errors import CaptureError
from core.model import Frame, Region

try:
    import mss
    from mss.exception import ScreenShotError
except ImportError as exc:  # pragma: no cover - exercised only without mss
    raise CaptureError("the 'mss' screen-capture library is not installed") from exc


class ScreenCapturer:
    """Grabs RGB frames from one monitor, blanking any excluded regions.

    mss state is not thread-safe, so ``start`` must be called on the same
    thread that calls ``grab`` — the recorder worker thread owns it.
    """

    def __init__(self, monitor_index: int, exclude: list[Region] | None = None) -> None:
        self._monitor_index = monitor_index
        self._exclude: list[Region] = list(exclude or [])
        self._sct: object | None = None
        self._monitor: dict[str, int] | None = None
        self._geometry: tuple[int, int] | None = None

    def start(self) -> None:
        try:
            sct = mss.MSS()
            monitors = sct.monitors
        except (ScreenShotError, OSError) as exc:
            raise CaptureError(f"could not initialize screen capture: {exc}") from exc
        if self._monitor_index < 0 or self._monitor_index >= len(monitors):
            raise CaptureError(
                f"monitor {self._monitor_index} not found "
                f"(have {len(monitors) - 1} display(s))"
            )
        self._sct = sct
        self._monitor = monitors[self._monitor_index]
        self._geometry = (int(self._monitor["width"]), int(self._monitor["height"]))

    @property
    def geometry(self) -> tuple[int, int]:
        if self._geometry is None:
            raise CaptureError("capturer not started")
        return self._geometry

    def grab(self) -> Frame:
        if self._sct is None or self._monitor is None:
            raise CaptureError("capturer not started")
        try:
            shot = self._sct.grab(self._monitor)  # type: ignore[attr-defined]
            raw = np.frombuffer(shot.bgra, dtype=np.uint8)
            bgra = raw.reshape(shot.height, shot.width, 4)
        except (ScreenShotError, OSError, ValueError) as exc:
            raise CaptureError(f"screen grab failed: {exc}") from exc
        rgb = np.ascontiguousarray(bgra[:, :, 2::-1])  # BGRA -> RGB
        self.blank_regions(rgb, self._exclude)
        return rgb

    @staticmethod
    def blank_regions(frame: Frame, regions: list[Region]) -> None:
        """Zero out each region in place, clamped to the frame bounds.

        Called on every grab before diffing or storage, so an excluded area
        is constant black in every frame and never produces a delta to store.
        """
        height, width = frame.shape[:2]
        for region in regions:
            clamped = region.clamped(width, height)
            if clamped.area > 0:
                frame[
                    clamped.y : clamped.y + clamped.h,
                    clamped.x : clamped.x + clamped.w,
                ] = 0

    def close(self) -> None:
        if self._sct is not None:
            try:
                self._sct.close()  # type: ignore[attr-defined]
            except (ScreenShotError, OSError):
                pass
            self._sct = None
