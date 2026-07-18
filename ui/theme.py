from __future__ import annotations

from pathlib import Path

from core.config import RESOURCES_DIR


def load_stylesheet(accent_hex: str) -> str:
    qss_path: Path = RESOURCES_DIR / "theme.qss"
    return qss_path.read_text(encoding="utf-8").replace("{ACCENT}", accent_hex)
