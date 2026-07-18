from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from core.activity import ActivityProfile


class ActivityHeatmap(QWidget):
    """A wall-clock heat band over a recording: when the screen was busy.

    Each column is a time bucket coloured by how much of the screen changed in
    it, so idle stretches read dark and busy stretches glow toward the accent.
    It doubles as a coarse scrubber — a click seeks to the nearest change event
    — and prints the peak "active hours" window beneath the band.
    """

    seekRequested = Signal(int)

    _MARGIN = 16  # matches ChangeTimeline so columns line up with its ticks
    _BAND_TOP = 8
    _BAND_BOTTOM_PAD = 22  # room for wall-clock labels under the band

    def __init__(self, accent_hex: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = QColor(accent_hex)
        self._profile: ActivityProfile | None = None
        self._event_offsets: list[int] = []
        self._current = 0
        self._hover = -1
        self.setMinimumHeight(72)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # -- public API ----------------------------------------------------------

    def set_profile(self, profile: ActivityProfile, event_offsets: list[int]) -> None:
        self._profile = profile
        self._event_offsets = list(event_offsets)
        self._current = 0
        self._hover = -1
        self.update()

    def set_current(self, index: int) -> None:
        if 0 <= index < len(self._event_offsets):
            self._current = index
            self.update()

    def clear(self) -> None:
        self._profile = None
        self._event_offsets = []
        self._current = 0
        self._hover = -1
        self.update()

    # -- geometry ------------------------------------------------------------

    def _band_rect(self) -> QRectF:
        width = self.width() - 2 * self._MARGIN
        height = self.height() - self._BAND_TOP - self._BAND_BOTTOM_PAD
        return QRectF(self._MARGIN, self._BAND_TOP, max(0.0, width), max(0.0, height))

    def _x_for_offset(self, offset_ms: int) -> float:
        band = self._band_rect()
        duration = self._profile.duration_ms if self._profile else 0
        frac = (offset_ms / duration) if duration > 0 else 0.0
        return band.x() + frac * band.width()

    def _offset_for_x(self, x: float) -> int:
        band = self._band_rect()
        duration = self._profile.duration_ms if self._profile else 0
        if band.width() <= 0 or duration <= 0:
            return 0
        frac = min(1.0, max(0.0, (x - band.x()) / band.width()))
        return int(frac * duration)

    def _bucket_at(self, x: float) -> int:
        if self._profile is None:
            return -1
        band = self._band_rect()
        buckets = self._profile.buckets
        if not buckets or band.width() <= 0:
            return -1
        frac = (x - band.x()) / band.width()
        if frac < 0.0 or frac > 1.0:
            return -1
        return min(len(buckets) - 1, max(0, int(frac * len(buckets))))

    def _heat_color(self, intensity: float) -> QColor:
        if intensity <= 0.0:
            return QColor("#16181d")
        # sqrt lifts faint activity so a few changed tiles still register.
        t = math.sqrt(min(1.0, intensity))
        cold = (32, 34, 40)
        hot = (self._accent.red(), self._accent.green(), self._accent.blue())
        return QColor(
            int(cold[0] + (hot[0] - cold[0]) * t),
            int(cold[1] + (hot[1] - cold[1]) * t),
            int(cold[2] + (hot[2] - cold[2]) * t),
        )

    # -- painting ------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        band = self._band_rect()

        if self._profile is None or self._profile.is_empty or band.width() <= 0:
            painter.fillRect(band, QColor("#101113"))
            painter.setPen(QPen(QColor("#5b5f66"), 1))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "No activity to map"
            )
            painter.end()
            return

        self._draw_band(painter, band)
        self._draw_peak_window(painter, band)
        self._draw_current(painter, band)
        self._draw_labels(painter, band)
        if self._hover >= 0:
            self._draw_hover(painter, band)
        painter.end()

    def _draw_band(self, painter: QPainter, band: QRectF) -> None:
        assert self._profile is not None
        for bucket in self._profile.buckets:
            x0 = self._x_for_offset(bucket.start_offset_ms)
            x1 = self._x_for_offset(bucket.end_offset_ms)
            rect = QRectF(x0, band.y(), max(1.0, x1 - x0), band.height())
            painter.fillRect(rect, self._heat_color(bucket.intensity))
        painter.setPen(QPen(QColor("#2a2c31"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(band)

    def _draw_peak_window(self, painter: QPainter, band: QRectF) -> None:
        assert self._profile is not None
        if self._profile.peak_fraction <= 0.0:
            return
        x0 = int(self._x_for_offset(self._profile.peak_start_offset_ms))
        x1 = int(self._x_for_offset(self._profile.peak_end_offset_ms))
        y = int(band.bottom()) + 3
        painter.setPen(QPen(self._accent, 2))
        painter.drawLine(x0, y, x1, y)
        painter.drawLine(x0, y - 3, x0, y + 1)
        painter.drawLine(x1, y - 3, x1, y + 1)

    def _draw_current(self, painter: QPainter, band: QRectF) -> None:
        if not self._event_offsets:
            return
        index = min(self._current, len(self._event_offsets) - 1)
        x = int(self._x_for_offset(self._event_offsets[index]))
        painter.setPen(QPen(QColor(255, 255, 255, 190), 1))
        painter.drawLine(x, int(band.y()), x, int(band.bottom()))

    def _draw_labels(self, painter: QPainter, band: QRectF) -> None:
        assert self._profile is not None
        profile = self._profile
        baseline = self.height() - 6
        metrics = painter.fontMetrics()

        painter.setPen(QPen(QColor("#5b5f66"), 1))
        painter.drawText(int(band.x()), baseline, profile.fmt_clock(0))
        end_label = profile.fmt_clock(profile.duration_ms)
        painter.drawText(
            int(band.right()) - metrics.horizontalAdvance(end_label), baseline, end_label
        )

        peak_label = profile.peak_window_label()
        peak_width = metrics.horizontalAdvance(peak_label)
        painter.setPen(QPen(self._accent, 1))
        painter.drawText(int(band.center().x() - peak_width / 2), baseline, peak_label)

    def _draw_hover(self, painter: QPainter, band: QRectF) -> None:
        assert self._profile is not None
        if self._hover >= len(self._profile.buckets):
            return
        bucket = self._profile.buckets[self._hover]
        x0 = self._x_for_offset(bucket.start_offset_ms)
        x1 = self._x_for_offset(bucket.end_offset_ms)
        painter.setPen(QPen(QColor(255, 255, 255, 140), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(x0, band.y(), max(1.0, x1 - x0), band.height()))

    # -- interaction ---------------------------------------------------------

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._profile is None or self._profile.is_empty:
            return
        index = self._bucket_at(event.position().x())
        if index == self._hover:
            return
        self._hover = index
        if 0 <= index < len(self._profile.buckets):
            bucket = self._profile.buckets[index]
            start = self._profile.fmt_clock(bucket.start_offset_ms)
            end = self._profile.fmt_clock(bucket.end_offset_ms)
            pct = round(bucket.intensity * 100)
            self.setToolTip(f"{start}–{end} · {pct}% of peak activity")
        self.update()

    def leaveEvent(self, event: QEvent) -> None:
        if self._hover != -1:
            self._hover = -1
            self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            self._profile is None
            or self._profile.is_empty
            or not self._event_offsets
            or event.button() != Qt.MouseButton.LeftButton
        ):
            return
        offset = self._offset_for_x(event.position().x())
        nearest = min(
            range(len(self._event_offsets)),
            key=lambda i: abs(self._event_offsets[i] - offset),
        )
        self.seekRequested.emit(nearest)
