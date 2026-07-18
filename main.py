from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from core.config import Config, RESOURCES_DIR, load_settings
from core.logging_setup import configure_logging
from ui.main_window import MainWindow
from ui.theme import load_stylesheet


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    config = Config()
    logger = configure_logging(config.app_name)
    logger.info("Starting %s %s", config.app_name, config.version)

    settings = load_settings()

    app = QApplication(sys.argv)
    app.setApplicationName(config.app_name)

    # Branded taskbar/window icon. Set at the app level so every window inherits
    # it; the system-tray icon stays procedural because it recolors while
    # recording. Absent .ico (e.g. a source checkout before a build) is fine.
    icon_path = RESOURCES_DIR / "icons" / "app.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    app.setStyleSheet(load_stylesheet(config.accent_hex))

    window = MainWindow(config, settings)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
