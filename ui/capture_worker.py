from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core.capture import ScreenCapturer
from core.errors import StutterboxError
from core.model import Frame, Region
from core.recorder import Recorder, RecorderConfig, RecordingStats

logger = logging.getLogger(__name__)


class CaptureWorker(QThread):
    """Runs the capture loop off the UI thread.

    Cross-thread Qt signals deliver per-event progress and the final stats
    back to the main thread; ``stop`` flips a threading.Event the recorder
    polls between grabs.
    """

    eventRecorded = Signal(int, int)
    recordingFinished = Signal(object)
    recordingFailed = Signal(str)

    def __init__(
        self,
        *,
        temp_path: Path,
        final_path: Path,
        monitor: int,
        exclude: list[Region],
        config: RecorderConfig,
        capture_format: str,
    ) -> None:
        super().__init__()
        self._temp_path = temp_path
        self._final_path = final_path
        self._monitor = monitor
        self._exclude = exclude
        self._config = config
        self._capture_format = capture_format
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        capturer = ScreenCapturer(self._monitor, self._exclude)
        try:
            capturer.start()

            def grab() -> Frame | None:
                return capturer.grab()

            recorder = Recorder(
                temp_path=self._temp_path,
                final_path=self._final_path,
                geometry=capturer.geometry,
                grab=grab,
                config=self._config,
                monitor=self._monitor,
                capture_format=self._capture_format,
            )
            stats: RecordingStats = recorder.run(
                self._stop,
                on_event=lambda ts, n: self.eventRecorded.emit(ts, n),
            )
            self.recordingFinished.emit(stats)
        except StutterboxError as exc:
            self.recordingFailed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - keep an errant grab off the GUI
            # Anything non-domain (an OSError on replace, an out-of-memory, a
            # backend quirk) must still surface as a failure, never a dead
            # thread that leaves the UI wedged on "Finalizing…".
            logger.exception("capture loop crashed")
            self.recordingFailed.emit(f"unexpected capture error: {exc}")
        finally:
            capturer.close()
