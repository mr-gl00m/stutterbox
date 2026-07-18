from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget


class ChangeTimeline(QWidget):
    """A scrubber whose ticks are change events, not uniform seconds.

    Ticks sit at their real time position so idle gaps are visible, but a
    click snaps to the nearest event and navigation steps tick-to-tick.
    """

    seekRequested = Signal(int)

    _MARGIN = 16
    _BASELINE_FROM_BOTTOM = 18

    def __init__(self, accent_hex: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = QColor(accent_hex)
        self._ts: list[int] = []
        self._current = 0
        self._duration_ms = 1
        self.setMinimumHeight(64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_events(self, ts_list: list[int]) -> None:
        self._ts = list(ts_list)
        self._duration_ms = max(self._ts[-1], 1) if self._ts else 1
        self._current = 0
        self.update()

    def append_event(self, ts_ms: int) -> None:
        self._ts.append(ts_ms)
        self._duration_ms = max(self._duration_ms, ts_ms, 1)
        self.update()

    def clear(self) -> None:
        self._ts = []
        self._current = 0
        self._duration_ms = 1
        self.update()

    def set_current(self, index: int) -> None:
        if 0 <= index < len(self._ts):
            self._current = index
            self.update()

    def _x_for_ts(self, ts_ms: int) -> float:
        width = self.width() - 2 * self._MARGIN
        return self._MARGIN + (ts_ms / self._duration_ms) * width

    def _baseline_y(self) -> float:
        return self.height() - self._BASELINE_FROM_BOTTOM

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        baseline = self._baseline_y()

        # Baseline.
        painter.setPen(QPen(QColor("#2a2c31"), 1))
        painter.drawLine(
            self._MARGIN, int(baseline), self.width() - self._MARGIN, int(baseline)
        )

        self._draw_time_grid(painter, baseline)

        if not self._ts:
            painter.setPen(QPen(QColor("#5b5f66"), 1))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "No change events",
            )
            painter.end()
            return

        # Event ticks.
        tick_pen = QPen(self._accent, 1)
        for index, ts in enumerate(self._ts):
            if index == self._current:
                continue
            x = self._x_for_ts(ts)
            painter.setPen(tick_pen)
            painter.drawLine(int(x), int(baseline) - 10, int(x), int(baseline))

        # Current event marker: taller, with a head triangle.
        cx = self._x_for_ts(self._ts[self._current])
        painter.setPen(QPen(self._accent, 2))
        painter.drawLine(int(cx), int(baseline) - 22, int(cx), int(baseline))
        head = QRectF(cx - 4, baseline - 28, 8, 8)
        painter.fillRect(head, self._accent)
        painter.end()

    def _draw_time_grid(self, painter: QPainter, baseline: float) -> None:
        seconds = self._duration_ms / 1000.0
        if seconds <= 0:
            return
        step = self._nice_step(seconds)
        painter.setPen(QPen(QColor("#202227"), 1))
        label_pen = QPen(QColor("#5b5f66"), 1)
        marks = int(seconds // step) + 1
        for i in range(marks + 1):
            t = i * step
            x = self._x_for_ts(int(t * 1000))
            painter.setPen(QPen(QColor("#202227"), 1))
            painter.drawLine(int(x), self._MARGIN, int(x), int(baseline))
            painter.setPen(label_pen)
            painter.drawText(int(x) + 2, self.height() - 4, self._fmt(t))

    @staticmethod
    def _nice_step(seconds: float) -> float:
        target = seconds / 8.0
        for candidate in (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600):
            if candidate >= target:
                return float(candidate)
        return 3600.0

    @staticmethod
    def _fmt(seconds: float) -> str:
        total = int(seconds)
        minutes, secs = divmod(total, 60)
        return f"{minutes}:{secs:02d}"

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._ts or event.button() != Qt.MouseButton.LeftButton:
            return
        click_x = event.position().x()
        nearest = min(
            range(len(self._ts)),
            key=lambda i: abs(self._x_for_ts(self._ts[i]) - click_x),
        )
        self.seekRequested.emit(nearest)
