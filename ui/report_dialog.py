from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.config import SETTINGS_PATH, Settings, save_settings
from core.container import RecordingReader
from core.errors import ReportError, StutterboxError
from core.model import ChangeEvent, Region
from core.report import (
    MAX_REPORT_FRAMES,
    REPORT_MODEL,
    PreparedReport,
    ReportKind,
    generate_report,
    prepare_report,
)


class ReportWorker(QThread):
    reportReady = Signal(str)
    reportFailed = Signal(str)

    def __init__(
        self,
        api_key: str,
        prepared: PreparedReport,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api_key = api_key
        self._prepared: PreparedReport | None = prepared

    def run(self) -> None:
        prepared = self._prepared
        if prepared is None:
            return
        try:
            report = generate_report(self._api_key, prepared)
        except ReportError as exc:
            self.reportFailed.emit(str(exc))
        except BaseException:
            self.reportFailed.emit("Report generation failed unexpectedly.")
        else:
            self.reportReady.emit(report)
        finally:
            self._api_key = ""
            self._prepared = None


class ReportDialog(QDialog):
    """Select a recording range and render a GPT-5.6 Markdown report."""

    def __init__(
        self,
        reader: RecordingReader,
        settings: Settings,
        redactions: list[Region],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Generate report")
        self.resize(820, 720)
        self._reader = reader
        self._settings = settings
        self._redactions = list(redactions)
        self._events: list[ChangeEvent] = reader.events
        self._worker: ReportWorker | None = None
        self._markdown = ""

        self._kind = QComboBox()
        self._kind.addItem("Bug reproduction report", "bug_repro")
        self._kind.addItem("Session summary", "session_summary")

        self._start_event = QSpinBox()
        self._end_event = QSpinBox()
        self._start_event.setRange(1, len(self._events))
        self._end_event.setRange(1, len(self._events))
        self._start_event.setValue(1)
        self._end_event.setValue(len(self._events))
        self._start_event.valueChanged.connect(self._update_range_label)
        self._end_event.valueChanged.connect(self._update_range_label)

        self._range_label = QLabel()
        self._api_key = QLineEdit(settings.openai_api_key)
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("sk-...")
        self._consent = QCheckBox(
            "I approve uploading these redacted frames to OpenAI for this report."
        )

        self._generate_button = QPushButton(f"Generate with {REPORT_MODEL}")
        self._generate_button.clicked.connect(self._on_generate)
        self._copy_button = QPushButton("Copy report")
        self._copy_button.setEnabled(False)
        self._copy_button.clicked.connect(self._on_copy)
        self._close_button = QPushButton("Close")
        self._close_button.clicked.connect(self.reject)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._status = QLabel("Ready")

        self._report = QTextBrowser()
        self._report.setPlaceholderText("The rendered Markdown report appears here.")
        self._build_ui()
        self._update_range_label()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            f"Stutterbox samples up to {MAX_REPORT_FRAMES} change-event frames from "
            "the selected range. Frames are reconstructed and redacted locally "
            "before the request is built."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.addRow("Report type", self._kind)

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("Event"))
        range_row.addWidget(self._start_event)
        range_row.addWidget(QLabel("to"))
        range_row.addWidget(self._end_event)
        form.addRow("Range", range_row)
        form.addRow("Timestamps", self._range_label)
        form.addRow("Model", QLabel(REPORT_MODEL))
        form.addRow("OpenAI API key", self._api_key)
        layout.addLayout(form)

        key_note = QLabel(
            f"The key is saved in local settings at {SETTINGS_PATH}. It is never "
            "written inside the repository or a recording."
        )
        key_note.setWordWrap(True)
        layout.addWidget(key_note)

        redaction_count = len(self._redactions)
        redaction_note = QLabel(
            f"Redaction pass: {redaction_count} marked region(s). The pass runs on "
            "every selected frame, including when no regions are marked."
        )
        redaction_note.setWordWrap(True)
        layout.addWidget(redaction_note)
        layout.addWidget(self._consent)

        controls = QHBoxLayout()
        controls.addWidget(self._generate_button)
        controls.addWidget(self._copy_button)
        controls.addStretch(1)
        controls.addWidget(self._close_button)
        layout.addLayout(controls)
        layout.addWidget(self._progress)
        layout.addWidget(self._status)
        layout.addWidget(self._report, stretch=1)

    def _update_range_label(self) -> None:
        start = self._start_event.value() - 1
        end = self._end_event.value() - 1
        if start > end:
            self._range_label.setText("Start must be at or before end.")
            return
        self._range_label.setText(
            f"{self._format_ts(self._events[start].ts_ms)} to "
            f"{self._format_ts(self._events[end].ts_ms)}"
        )

    def _on_generate(self) -> None:
        if self._worker is not None:
            return
        key = self._api_key.text().strip()
        if not key:
            QMessageBox.warning(self, "OpenAI API key", "Add an API key first.")
            return
        if not self._consent.isChecked():
            QMessageBox.warning(
                self,
                "Cloud upload approval",
                "Approve the redacted frame upload before generating a report.",
            )
            return

        start = self._start_event.value() - 1
        end = self._end_event.value() - 1
        if start > end:
            QMessageBox.warning(self, "Event range", "Choose a valid event range.")
            return

        self._settings.openai_api_key = key
        try:
            save_settings(self._settings)
        except OSError as exc:
            QMessageBox.warning(self, "Settings", f"Could not save the API key: {exc}")
            return

        report_kind: ReportKind = (
            "bug_repro"
            if self._kind.currentData() == "bug_repro"
            else "session_summary"
        )
        self._status.setText("Reconstructing and redacting selected frames...")
        QApplication.processEvents()
        try:
            prepared = prepare_report(
                self._reader,
                start,
                end,
                report_kind=report_kind,
                redactions=self._redactions,
            )
        except (StutterboxError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Report preparation", str(exc))
            self._status.setText("Report preparation failed.")
            return

        worker = ReportWorker(key, prepared, self)
        worker.reportReady.connect(self._on_report_ready)
        worker.reportFailed.connect(self._on_report_failed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        self._set_generating(True)
        self._status.setText(
            f"Uploading {len(prepared.snapshots)} redacted frame(s) to {REPORT_MODEL}..."
        )
        worker.start()

    def _on_report_ready(self, markdown: str) -> None:
        self._markdown = markdown
        self._report.setMarkdown(markdown)
        self._copy_button.setEnabled(True)
        self._status.setText("Report ready.")

    def _on_report_failed(self, reason: str) -> None:
        QMessageBox.warning(self, "Report generation", reason)
        self._status.setText("Report generation failed.")

    def _on_worker_finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        self._set_generating(False)

    def _set_generating(self, generating: bool) -> None:
        self._progress.setVisible(generating)
        self._generate_button.setEnabled(not generating)
        self._close_button.setEnabled(not generating)
        self._kind.setEnabled(not generating)
        self._start_event.setEnabled(not generating)
        self._end_event.setEnabled(not generating)
        self._api_key.setEnabled(not generating)
        self._consent.setEnabled(not generating)

    def _on_copy(self) -> None:
        if self._markdown:
            QApplication.clipboard().setText(self._markdown)
            self._status.setText("Copied report Markdown to the clipboard.")

    def reject(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._status.setText("Report generation is still running.")
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._status.setText("Report generation is still running.")
            event.ignore()
            return
        super().closeEvent(event)

    @staticmethod
    def _format_ts(ts_ms: int) -> str:
        seconds, millis = divmod(ts_ms, 1000)
        minutes, secs = divmod(seconds, 60)
        return f"{minutes}:{secs:02d}.{millis:03d}"
