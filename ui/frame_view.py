from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QWidget

from core.model import Region


class FrameView(QWidget):
    """Shows a reconstructed frame scaled to fit, with optional redaction draw.

    When redaction mode is on, dragging marks a rectangle (in frame pixel
    coordinates) to blank on export — the regions persist across window
    resizes because they are stored in frame space, not widget space.
    """

    def __init__(self, accent_hex: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = QColor(accent_hex)
        self._image: QImage | None = None
        self._selection_enabled = False
        self._drag_origin: QPointF | None = None
        self._drag_current: QPointF | None = None
        self._redactions: list[Region] = []
        self.setMinimumSize(480, 320)

    # -- public API ----------------------------------------------------------

    def set_image(self, image: QImage) -> None:
        self._image = image
        self.update()

    def clear(self) -> None:
        self._image = None
        self.update()

    def set_selection_enabled(self, enabled: bool) -> None:
        self._selection_enabled = enabled
        self._drag_origin = None
        self._drag_current = None
        self.setCursor(
            Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor
        )
        self.update()

    def redactions(self) -> list[Region]:
        return list(self._redactions)

    def set_redactions(self, regions: list[Region]) -> None:
        self._redactions = list(regions)
        self.update()

    def clear_redactions(self) -> None:
        self._redactions = []
        self.update()

    # -- geometry ------------------------------------------------------------

    def _image_rect(self) -> QRectF:
        if self._image is None:
            return QRectF()
        iw, ih = self._image.width(), self._image.height()
        if iw <= 0 or ih <= 0:
            return QRectF()
        scale = min(self.width() / iw, self.height() / ih)
        dw, dh = iw * scale, ih * scale
        ox = (self.width() - dw) / 2.0
        oy = (self.height() - dh) / 2.0
        return QRectF(ox, oy, dw, dh)

    def _widget_to_frame(self, point: QPointF) -> tuple[int, int]:
        rect = self._image_rect()
        assert self._image is not None
        iw, ih = self._image.width(), self._image.height()
        scale = rect.width() / iw if iw else 1.0
        fx = (point.x() - rect.x()) / scale if scale else 0.0
        fy = (point.y() - rect.y()) / scale if scale else 0.0
        return (
            max(0, min(int(round(fx)), iw)),
            max(0, min(int(round(fy)), ih)),
        )

    def _frame_to_widget(self, region: Region) -> QRectF:
        rect = self._image_rect()
        assert self._image is not None
        iw = self._image.width()
        scale = rect.width() / iw if iw else 1.0
        return QRectF(
            rect.x() + region.x * scale,
            rect.y() + region.y * scale,
            region.w * scale,
            region.h * scale,
        )

    # -- painting ------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0c0d0f"))
        if self._image is None:
            painter.setPen(QPen(QColor("#5b5f66"), 1))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Press Record to capture, or Open a recording",
            )
            painter.end()
            return

        target = self._image_rect()
        painter.drawImage(target, self._image)

        # Existing redaction rectangles.
        fill = QColor(self._accent)
        fill.setAlpha(70)
        for region in self._redactions:
            wrect = self._frame_to_widget(region)
            painter.fillRect(wrect, fill)
            painter.setPen(QPen(self._accent, 1))
            painter.drawRect(wrect)

        # In-progress drag rectangle.
        if self._drag_origin is not None and self._drag_current is not None:
            rubber = QRectF(self._drag_origin, self._drag_current).normalized()
            painter.setPen(QPen(self._accent, 1, Qt.PenStyle.DashLine))
            painter.drawRect(rubber)
        painter.end()

    # -- interaction ---------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            not self._selection_enabled
            or self._image is None
            or event.button() != Qt.MouseButton.LeftButton
        ):
            return
        self._drag_origin = event.position()
        self._drag_current = event.position()
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_origin is not None:
            self._drag_current = event.position()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_origin is None or self._drag_current is None:
            return
        x0, y0 = self._widget_to_frame(self._drag_origin)
        x1, y1 = self._widget_to_frame(self._drag_current)
        self._drag_origin = None
        self._drag_current = None
        rx, ry = min(x0, x1), min(y0, y1)
        rw, rh = abs(x1 - x0), abs(y1 - y0)
        if rw > 0 and rh > 0:
            self._redactions.append(Region(rx, ry, rw, rh))
        self.update()
