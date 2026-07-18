from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QCloseEvent, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from core.activity import ActivityProfile, build_profile
from core.config import Config, Settings, save_settings
from core.errors import ContainerError, CorruptRecordingError, StutterboxError
from core.paths import validate_within_root
from core.model import Frame
from core.player import Player
from core.recorder import RecorderConfig, RecordingStats
from core.redaction import export_recording
from ui.capture_worker import CaptureWorker
from ui.dialogs import ExcludeRegionsDialog
from ui.frame_view import FrameView
from ui.heatmap import ActivityHeatmap
from ui.qt_image import frame_to_qimage
from ui.report_dialog import ReportDialog
from ui.timeline import ChangeTimeline

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Recorder and change-event player in one window.

    The primary driver is the timeline scrubber plus the recording controls;
    copy-current-frame and copy-share-snippet are the first-class secondary
    actions, per the charter.
    """

    def __init__(self, config: Config, settings: Settings) -> None:
        super().__init__()
        self._config = config
        self._settings = settings
        self._player: Player | None = None
        self._worker: CaptureWorker | None = None
        self._recording = False
        self._event_count = 0
        self._current_image: QImage | None = None
        self._tray: QSystemTrayIcon | None = None
        self._tray_record_action: QAction | None = None
        self._tray_notified = False

        # Widgets assigned in _init_ui.
        self._record_button: QPushButton
        self._stop_button: QPushButton
        self._open_button: QPushButton
        self._export_button: QPushButton
        self._report_button: QPushButton
        self._redact_button: QPushButton
        self._clear_redactions_button: QPushButton
        self._exclude_button: QPushButton
        self._copy_frame_button: QPushButton
        self._copy_snippet_button: QPushButton
        self._prev_button: QPushButton
        self._next_button: QPushButton
        self._indicator: QLabel
        self._event_info: QLabel
        self._frame_view: FrameView
        self._heatmap: ActivityHeatmap
        self._timeline: ChangeTimeline
        self._status: QStatusBar

        self._init_ui()
        self._update_controls()

    # -- construction --------------------------------------------------------

    def _init_ui(self) -> None:
        self.setWindowTitle(self._config.app_name)
        self.resize(self._config.window_width, self._config.window_height)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        root.addLayout(self._build_control_row())

        self._frame_view = FrameView(self._config.accent_hex)
        root.addWidget(self._frame_view, stretch=1)

        root.addLayout(self._build_nav_row())

        self._heatmap = ActivityHeatmap(self._config.accent_hex)
        self._heatmap.seekRequested.connect(self._on_seek)
        root.addWidget(self._heatmap)

        self._timeline = ChangeTimeline(self._config.accent_hex)
        self._timeline.seekRequested.connect(self._on_seek)
        root.addWidget(self._timeline)

        self.setCentralWidget(central)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready")

        self._init_tray()

    # -- system tray ---------------------------------------------------------

    def _init_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.info("system tray unavailable; minimize-to-tray disabled")
            return

        idle_icon = self._tray_pixmap(recording=False)

        tray = QSystemTrayIcon(idle_icon, self)
        tray.setToolTip(f"{self._config.app_name} — idle")

        menu = QMenu()
        show_action = QAction("Show Stutterbox", self)
        show_action.triggered.connect(self._restore_window)
        self._tray_record_action = QAction("Start recording", self)
        self._tray_record_action.triggered.connect(self._toggle_record_from_tray)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        menu.addAction(show_action)
        menu.addAction(self._tray_record_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self._tray = tray

    def _tray_pixmap(self, *, recording: bool) -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        accent = QColor(self._config.accent_hex)
        painter.setBrush(accent if recording else QColor("#c9ccd1"))
        painter.drawEllipse(12, 12, 40, 40)
        painter.end()
        return QIcon(pixmap)

    def _update_tray(self) -> None:
        if self._tray is None:
            return
        self._tray.setIcon(self._tray_pixmap(recording=self._recording))
        self._tray.setToolTip(
            f"{self._config.app_name} — {'recording' if self._recording else 'idle'}"
        )
        if self._tray_record_action is not None:
            self._tray_record_action.setText(
                "Stop recording" if self._recording else "Start recording"
            )

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._restore_window()

    def _restore_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _hide_to_tray(self) -> None:
        self.hide()
        if self._tray is not None and not self._tray_notified:
            self._tray.showMessage(
                self._config.app_name,
                "Still recording — in the tray."
                if self._recording
                else "Running in the tray.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
            self._tray_notified = True

    def _toggle_record_from_tray(self) -> None:
        if self._recording:
            self._on_stop()
        else:
            self._on_record()

    def _build_control_row(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self._record_button = QPushButton("Record")
        self._record_button.setObjectName("RecordButton")
        self._record_button.clicked.connect(self._on_record)

        self._stop_button = QPushButton("Stop")
        self._stop_button.clicked.connect(self._on_stop)

        self._open_button = QPushButton("Open")
        self._open_button.clicked.connect(self._on_open)

        self._export_button = QPushButton("Export")
        self._export_button.clicked.connect(self._on_export)

        self._report_button = QPushButton("Generate report")
        self._report_button.clicked.connect(self._on_generate_report)

        self._redact_button = QPushButton("Redact")
        self._redact_button.setCheckable(True)
        self._redact_button.toggled.connect(self._on_redact_toggled)

        self._clear_redactions_button = QPushButton("Clear redactions")
        self._clear_redactions_button.clicked.connect(self._on_clear_redactions)

        self._exclude_button = QPushButton("Exclude regions")
        self._exclude_button.clicked.connect(self._on_exclude_regions)

        self._copy_frame_button = QPushButton("Copy frame")
        self._copy_frame_button.clicked.connect(self._on_copy_frame)

        self._copy_snippet_button = QPushButton("Copy share snippet")
        self._copy_snippet_button.clicked.connect(self._on_copy_snippet)

        for button in (
            self._record_button,
            self._stop_button,
            self._open_button,
            self._export_button,
            self._report_button,
            self._redact_button,
            self._clear_redactions_button,
            self._exclude_button,
            self._copy_frame_button,
            self._copy_snippet_button,
        ):
            row.addWidget(button)

        row.addStretch(1)

        self._indicator = QLabel("● REC")
        self._indicator.setStyleSheet(f"color: {self._config.accent_hex}; font-weight: 600;")
        self._indicator.setVisible(False)
        row.addWidget(self._indicator)
        return row

    def _build_nav_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._prev_button = QPushButton("‹ Previous change")
        self._prev_button.clicked.connect(self._on_prev)
        self._next_button = QPushButton("Next change ›")
        self._next_button.clicked.connect(self._on_next)
        row.addWidget(self._prev_button)
        row.addWidget(self._next_button)
        row.addStretch(1)
        self._event_info = QLabel("")
        self._event_info.setObjectName("MonoLabel")
        row.addWidget(self._event_info)
        return row

    # -- recording -----------------------------------------------------------

    def _on_record(self) -> None:
        if self._recording:
            return
        self._close_player()
        root = self._settings.recordings_root
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._warn("Cannot record", f"Recordings folder is unavailable: {exc}")
            return

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_path = root / f"rec_{stamp}.stut"
        temp_path = root / f".rec_{stamp}.stut.tmp"
        try:
            validate_within_root(final_path, root)
            validate_within_root(temp_path, root)
        except ContainerError as exc:
            self._warn("Cannot record", str(exc))
            return

        config = RecorderConfig(
            interval_ms=self._settings.interval_ms,
            diff_threshold=self._settings.diff_threshold,
            tile_size=self._settings.tile_size,
        )
        worker = CaptureWorker(
            temp_path=temp_path,
            final_path=final_path,
            monitor=self._settings.monitor,
            exclude=self._settings.exclude_as_regions(),
            config=config,
            capture_format=self._settings.capture_format,
        )
        worker.eventRecorded.connect(self._on_event_recorded)
        worker.recordingFinished.connect(self._on_recording_finished)
        worker.recordingFailed.connect(self._on_recording_failed)
        # Release the QThread only after run() has fully returned. The result
        # signals above fire from inside the still-running thread, so dropping
        # the reference in their handlers would GC a live QThread and Qt aborts
        # the process. finished() fires after the thread exits — safe to clean.
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker

        self._recording = True
        self._event_count = 0
        self._timeline.clear()
        self._heatmap.clear()
        self._frame_view.clear()
        self._current_image = None
        self._indicator.setVisible(True)
        self._update_controls()
        self._status.showMessage("Recording — 0 events")
        logger.info("Recording started -> %s", final_path)
        worker.start()

    def _on_event_recorded(self, ts_ms: int, region_count: int) -> None:
        self._event_count += 1
        self._timeline.append_event(ts_ms)
        self._status.showMessage(f"Recording — {self._event_count} events")

    def _on_stop(self) -> None:
        if self._worker is not None and self._recording:
            self._status.showMessage("Finalizing…")
            self._stop_button.setEnabled(False)
            self._worker.stop()

    def _on_recording_finished(self, stats: RecordingStats) -> None:
        self._recording = False
        self._indicator.setVisible(False)
        logger.info(
            "Recording finished: %d events, %d frames, %d blob bytes -> %s",
            stats.event_count,
            stats.frame_count,
            stats.blob_bytes,
            stats.path,
        )
        kib = stats.blob_bytes / 1024.0
        saved_prefix = (
            "Stopped at disk safety floor. Saved"
            if stats.stopped_for_low_disk
            else "Saved"
        )
        self._status.showMessage(
            f"{saved_prefix} {stats.path.name}: {stats.event_count} events, "
            f"{stats.frame_count} frames, {kib:.1f} KiB"
        )
        # We just wrote this file, so it is trusted — skip the full hash-chain
        # re-verification, which would re-read and re-hash every frame on the
        # GUI thread and stall a long recording's auto-open.
        self._open_recording(stats.path, verify=False)
        self._update_controls()

    def _on_recording_failed(self, reason: str) -> None:
        self._recording = False
        self._indicator.setVisible(False)
        logger.error("Recording failed: %s", reason)
        self._warn("Recording failed", reason)
        self._status.showMessage("Recording failed")
        self._update_controls()

    def _on_worker_finished(self) -> None:
        # Runs after the worker thread's run() has returned, so the QThread is
        # no longer running and can be torn down without aborting the process.
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._recording:
            # The thread ended without a result signal (an unexpected, non
            # domain error escaped run()). Don't leave the UI stuck finalizing.
            self._recording = False
            self._indicator.setVisible(False)
            self._status.showMessage("Recording stopped unexpectedly")
            self._update_controls()

    # -- playback ------------------------------------------------------------

    def _on_open(self) -> None:
        start_dir = str(self._settings.recordings_root)
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open recording", start_dir, "Stutterbox recording (*.stut)"
        )
        if path_str:
            self._open_recording(Path(path_str))

    def _open_recording(self, path: Path, *, verify: bool = True) -> None:
        self._close_player()
        try:
            player = Player(path, verify=verify)
        except CorruptRecordingError as exc:
            self._warn("Recording rejected", exc.reason)
            self._status.showMessage(f"Rejected {path.name}: {exc.reason}")
            return
        except StutterboxError as exc:
            self._warn("Could not open recording", str(exc))
            return

        if player.event_count == 0:
            player.close()
            self._warn("Empty recording", "This recording has no change events.")
            return

        self._player = player
        self._redact_button.setChecked(False)
        self._frame_view.clear_redactions()
        self._timeline.set_events([event.ts_ms for event in player.events])
        profile, offsets = self._build_activity(player)
        self._heatmap.set_profile(profile, offsets)
        self._show_frame(player.seek(0))
        self._update_controls()
        active = "" if profile.is_empty else f", {profile.peak_window_label()}"
        self._status.showMessage(
            f"{path.name} — {player.event_count} change events, "
            f"{player.meta.width}x{player.meta.height}, chain verified{active}"
        )

    @staticmethod
    def _build_activity(player: Player) -> tuple[ActivityProfile, list[int]]:
        # Weight each bucket by changed-pixel area. Delta frames only — the
        # opening keyframe carries the whole screen and would otherwise drown
        # every real change in its area.
        samples = [
            (row.ts_ms, float(row.w * row.h))
            for row in player.reader.index
            if row.kind == "delta"
        ]
        events = player.events
        duration = events[-1].ts_ms if events else 0
        profile = build_profile(
            samples, created_ms=player.meta.created_ms, duration_ms=duration
        )
        return profile, [event.ts_ms for event in events]

    def _on_next(self) -> None:
        if self._player is not None and self._player.has_next():
            self._show_frame(self._player.next_change())

    def _on_prev(self) -> None:
        if self._player is not None and self._player.has_prev():
            self._show_frame(self._player.prev_change())

    def _on_seek(self, index: int) -> None:
        if self._player is not None:
            self._show_frame(self._player.seek(index))

    def _show_frame(self, frame: Frame) -> None:
        if self._player is None:
            return
        try:
            image = frame_to_qimage(frame)
        except (ValueError, CorruptRecordingError) as exc:
            self._warn("Frame error", str(exc))
            return
        self._current_image = image
        self._frame_view.set_image(image)
        self._timeline.set_current(self._player.current_index)
        self._heatmap.set_current(self._player.current_index)
        self._update_event_info()
        self._update_controls()

    def _update_event_info(self) -> None:
        if self._player is None:
            self._event_info.setText("")
            return
        event = self._player.current_event
        self._event_info.setText(
            f"event {event.index + 1}/{self._player.event_count}  ·  "
            f"{self._fmt_ts(event.ts_ms)}  ·  {event.region_count} region(s)"
        )

    # -- copy / export -------------------------------------------------------

    def _on_copy_frame(self) -> None:
        if self._current_image is None:
            return
        QApplication.clipboard().setImage(self._current_image)
        self._status.showMessage("Copied current frame to clipboard")

    def _on_copy_snippet(self) -> None:
        if self._player is None or self._current_image is None:
            return
        event = self._player.current_event
        meta = self._player.meta
        text = (
            f"Stutterbox recording — event {event.index + 1}/"
            f"{self._player.event_count} at {self._fmt_ts(event.ts_ms)}\n"
            f"{meta.width}x{meta.height}, {event.region_count} changed region(s)\n"
            f"captured by Stutterbox {meta.app_version}; hash chain verified on open"
        )
        mime = QMimeData()
        mime.setText(text)
        mime.setImageData(self._current_image)
        QApplication.clipboard().setMimeData(mime)
        self._status.showMessage("Copied share snippet to clipboard")

    def _on_redact_toggled(self, checked: bool) -> None:
        self._frame_view.set_selection_enabled(checked)
        if checked:
            self._status.showMessage("Drag on the frame to mark redaction regions")

    def _on_clear_redactions(self) -> None:
        self._frame_view.clear_redactions()
        self._status.showMessage("Cleared redaction regions")

    def _on_export(self) -> None:
        if self._player is None:
            return
        redactions = self._frame_view.redactions()
        if redactions:
            detail = (
                f"{len(redactions)} redaction region(s) will be baked into the "
                "exported copy and cannot be recovered."
            )
        else:
            detail = (
                "No redaction regions are marked. The export may contain "
                "on-screen secrets. Use Redact to mark areas first."
            )
        confirm = QMessageBox.question(
            self,
            "Export recording",
            "A recording can contain passwords, tokens, or other on-screen "
            f"secrets.\n\n{detail}\n\nContinue?",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if confirm != QMessageBox.StandardButton.Ok:
            return

        path_str, _ = QFileDialog.getSaveFileName(
            self, "Export to", "", "Stutterbox recording (*.stut)"
        )
        if not path_str:
            return
        dst = Path(path_str)
        if dst.suffix != ".stut":
            dst = dst.with_suffix(".stut")

        overwrite = False
        if dst.exists():
            replace = QMessageBox.question(
                self,
                "Replace recording",
                f"{dst.name} already exists. Replace it? This cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if replace != QMessageBox.StandardButton.Yes:
                return
            overwrite = True

        try:
            stats = export_recording(
                self._player.reader,
                dst,
                redactions=redactions,
                overwrite=overwrite,
            )
        except StutterboxError as exc:
            self._warn("Export failed", str(exc))
            return
        logger.info("Exported %s (%d redactions)", dst, stats.redacted_regions)
        self._status.showMessage(
            f"Exported {dst.name} — {stats.frame_count} frames, "
            f"{stats.redacted_regions} redacted"
        )

    def _on_generate_report(self) -> None:
        if self._player is None:
            return
        dialog = ReportDialog(
            self._player.reader,
            self._settings,
            self._frame_view.redactions(),
            parent=self,
        )
        dialog.exec()

    def _on_exclude_regions(self) -> None:
        geometry = None
        if self._player is not None:
            geometry = (self._player.meta.width, self._player.meta.height)
        dialog = ExcludeRegionsDialog(
            self._settings.exclude_as_regions(),
            monitor=self._settings.monitor,
            accent_hex=self._config.accent_hex,
            screen_geometry=geometry,
            parent=self,
        )
        if dialog.exec():
            self._settings.set_exclude_regions(dialog.result_regions())
            try:
                save_settings(self._settings)
            except OSError as exc:
                self._warn("Settings", f"Could not save exclude regions: {exc}")
                return
            self._status.showMessage(
                f"{len(self._settings.exclude_regions)} exclude region(s) saved"
            )

    # -- helpers -------------------------------------------------------------

    def _update_controls(self) -> None:
        has_player = self._player is not None
        self._record_button.setEnabled(not self._recording)
        self._stop_button.setEnabled(self._recording)
        self._open_button.setEnabled(not self._recording)
        self._export_button.setEnabled(has_player and not self._recording)
        self._report_button.setEnabled(has_player and not self._recording)
        self._redact_button.setEnabled(has_player and not self._recording)
        self._clear_redactions_button.setEnabled(has_player and not self._recording)
        self._exclude_button.setEnabled(not self._recording)
        self._copy_frame_button.setEnabled(has_player and self._current_image is not None)
        self._copy_snippet_button.setEnabled(
            has_player and self._current_image is not None
        )
        self._prev_button.setEnabled(has_player and self._player is not None and self._player.has_prev())
        self._next_button.setEnabled(has_player and self._player is not None and self._player.has_next())
        self._update_tray()

    def _close_player(self) -> None:
        if self._player is not None:
            self._player.close()
            self._player = None
        self._current_image = None
        self._heatmap.clear()
        self._event_info.setText("")

    def _warn(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    @staticmethod
    def _fmt_ts(ts_ms: int) -> str:
        seconds, millis = divmod(ts_ms, 1000)
        minutes, secs = divmod(seconds, 60)
        return f"{minutes}:{secs:02d}.{millis:03d}"

    def changeEvent(self, event: QEvent) -> None:
        # On minimize, drop off the taskbar into the tray. Defer the hide() so
        # it runs after the state change is fully applied.
        if (
            event.type() == QEvent.Type.WindowStateChange
            and self._tray is not None
            and self.isMinimized()
        ):
            QTimer.singleShot(0, self._hide_to_tray)
        super().changeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker is not None and self._recording:
            self._worker.stop()
            if not self._worker.wait(3000):
                self._status.showMessage(
                    "Capture is still finalizing. Close after it finishes."
                )
                event.ignore()
                return
        if self._tray is not None:
            self._tray.hide()
        self._close_player()
        super().closeEvent(event)
