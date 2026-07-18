from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from ui.main_window import MainWindow


class _SlowWorker:
    def __init__(self) -> None:
        self.stopped = False
        self.wait_timeout = 0

    def stop(self) -> None:
        self.stopped = True

    def wait(self, timeout: int) -> bool:
        self.wait_timeout = timeout
        return False


class _Status:
    def __init__(self) -> None:
        self.message = ""

    def showMessage(self, message: str) -> None:
        self.message = message


class _Tray:
    def __init__(self) -> None:
        self.hidden = False

    def hide(self) -> None:
        self.hidden = True


class _CloseEvent:
    def __init__(self) -> None:
        self.ignored = False

    def ignore(self) -> None:
        self.ignored = True


def test_close_is_deferred_while_capture_thread_is_live() -> None:
    worker = _SlowWorker()
    status = _Status()
    tray = _Tray()
    event: Any = _CloseEvent()
    window: Any = SimpleNamespace(
        _tray=tray,
        _worker=worker,
        _recording=True,
        _status=status,
    )

    MainWindow.closeEvent(window, event)

    assert worker.stopped
    assert worker.wait_timeout == 3000
    assert event.ignored
    assert not tray.hidden
    assert status.message == "Capture is still finalizing. Close after it finishes."
