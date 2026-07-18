from __future__ import annotations

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.capture import ScreenCapturer
from core.errors import CaptureError
from core.model import Region
from ui.frame_view import FrameView
from ui.qt_image import frame_to_qimage

_MAX_COORD = 16_384
# Time for our (transparent) windows to leave the composited desktop before
# the screenshot grab.
_SETTLE_S = 0.18


def _settle(seconds: float) -> None:
    """Pump the event loop briefly so a pending opacity/compositor change is
    applied before the grab — without freezing the GUI the way time.sleep would.
    """
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


class ExcludeRegionsDialog(QDialog):
    """Manage capture-time exclude regions.

    Anything listed here is blanked at grab time, so those screen areas are
    never written to a recording in the first place — distinct from the
    export-time redaction pass, which scrubs an already-captured recording.
    """

    def __init__(
        self,
        regions: list[Region],
        *,
        monitor: int,
        accent_hex: str,
        screen_geometry: tuple[int, int] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exclude regions from capture")
        self._regions: list[Region] = list(regions)
        self._monitor = monitor
        self._accent = accent_hex
        max_w = screen_geometry[0] if screen_geometry else _MAX_COORD
        max_h = screen_geometry[1] if screen_geometry else _MAX_COORD

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Regions listed here are blanked before capture and never\n"
                "stored. Box them on a screenshot, or enter pixels by hand."
            )
        )

        screenshot_button = QPushButton("Select on screenshot…")
        screenshot_button.clicked.connect(self._on_screenshot)
        layout.addWidget(screenshot_button)

        self._list = QListWidget()
        layout.addWidget(self._list)

        entry = QHBoxLayout()
        self._sx = self._make_spin(max_w)
        self._sy = self._make_spin(max_h)
        self._sw = self._make_spin(max_w)
        self._sh = self._make_spin(max_h)
        for label, spin in (
            ("x", self._sx),
            ("y", self._sy),
            ("w", self._sw),
            ("h", self._sh),
        ):
            entry.addWidget(QLabel(label))
            entry.addWidget(spin)
        add_button = QPushButton("Add")
        add_button.clicked.connect(self._on_add)
        entry.addWidget(add_button)
        layout.addLayout(entry)

        controls = QHBoxLayout()
        remove_button = QPushButton("Remove selected")
        remove_button.clicked.connect(self._on_remove)
        clear_button = QPushButton("Clear all")
        clear_button.clicked.connect(self._on_clear)
        controls.addWidget(remove_button)
        controls.addWidget(clear_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh()

    @staticmethod
    def _make_spin(maximum: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, maximum)
        return spin

    def _refresh(self) -> None:
        self._list.clear()
        for region in self._regions:
            self._list.addItem(
                f"x={region.x}  y={region.y}  w={region.w}  h={region.h}"
            )

    def _on_add(self) -> None:
        region = Region(
            self._sx.value(), self._sy.value(), self._sw.value(), self._sh.value()
        )
        if region.w > 0 and region.h > 0:
            self._regions.append(region)
            self._refresh()

    def _on_remove(self) -> None:
        row = self._list.currentRow()
        if 0 <= row < len(self._regions):
            del self._regions[row]
            self._refresh()

    def _on_clear(self) -> None:
        self._regions = []
        self._refresh()

    def _on_screenshot(self) -> None:
        image = self._capture_screenshot()
        if image is None:
            return
        picker = ScreenshotSelectDialog(
            image, self._accent, initial=self._regions, parent=self
        )
        if picker.exec():
            self._regions = picker.result_regions()
            self._refresh()

    def _capture_screenshot(self) -> QImage | None:
        # Make our own windows transparent instead of hiding them. Hiding a
        # window that is inside a modal exec() wedges the modal input grab on
        # Windows: control returns from the picker to a parent dialog that no
        # longer accepts input and the app looks frozen. Opacity keeps the
        # windows mapped — modality intact — while leaving them out of the shot.
        to_dim = [w for w in (self, self.parentWidget()) if w is not None]
        saved = [w.windowOpacity() for w in to_dim]
        for widget in to_dim:
            widget.setWindowOpacity(0.0)
        _settle(_SETTLE_S)

        capturer = ScreenCapturer(self._monitor)
        try:
            capturer.start()
            frame = capturer.grab()
        except CaptureError as exc:
            QMessageBox.warning(self, "Screenshot failed", str(exc))
            return None
        finally:
            capturer.close()
            for widget, opacity in zip(to_dim, saved):
                widget.setWindowOpacity(opacity)

        return frame_to_qimage(frame)

    def result_regions(self) -> list[Region]:
        return list(self._regions)


class ScreenshotSelectDialog(QDialog):
    """Box exclude regions visually on a freshly grabbed screenshot.

    Selections are in screen pixel coordinates because the screenshot is the
    whole monitor, so they map straight onto what capture grabs.
    """

    def __init__(
        self,
        image: QImage,
        accent_hex: str,
        initial: list[Region] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select regions to exclude")
        self.resize(1000, 680)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Drag to box each region to exclude from capture. "
                "Draw as many as you need."
            )
        )

        self._view = FrameView(accent_hex)
        self._view.set_image(image)
        self._view.set_selection_enabled(True)
        if initial:
            self._view.set_redactions(initial)
        layout.addWidget(self._view, stretch=1)

        controls = QHBoxLayout()
        clear_button = QPushButton("Clear selections")
        clear_button.clicked.connect(self._view.clear_redactions)
        controls.addWidget(clear_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_regions(self) -> list[Region]:
        return self._view.redactions()
