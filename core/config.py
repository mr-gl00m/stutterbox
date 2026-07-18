from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field, fields
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from core.io import atomic_write_json, read_json
from core.model import Region

APP_VERSION: str = "0.2.0"
MAX_SETTINGS_BYTES: int = 1024 * 1024
MAX_EXCLUDE_REGIONS: int = 128
MAX_SETTING_COORDINATE: int = 32_768


def _is_frozen() -> bool:
    """True when running from a PyInstaller build rather than source."""
    return bool(getattr(sys, "frozen", False))


def _bundle_root() -> Path:
    """Directory that bundled read-only resources resolve against.

    Under PyInstaller, data added in the spec lands in ``sys._MEIPASS`` (the
    ``_internal`` dir beside the exe for a onedir build). From source it is the
    project root. ``Path(__file__).parent.parent`` alone is wrong inside a
    frozen build, which is why ``RESOURCES_DIR``/``MIGRATIONS_DIR`` route here.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
BUNDLE_ROOT: Path = _bundle_root()
RESOURCES_DIR: Path = BUNDLE_ROOT / "resources"
MIGRATIONS_DIR: Path = BUNDLE_ROOT / "migrations"

# User state lives outside the repo so recordings (potentially sensitive) and
# settings are never accidentally committed.
USER_DATA_DIR: Path = Path.home() / ".proj_stutterbox"
SETTINGS_PATH: Path = USER_DATA_DIR / "settings.json"
DEFAULT_RECORDINGS_DIR: Path = USER_DATA_DIR / "recordings"

# Logs must land somewhere writable. Beside a frozen exe (e.g. under Program
# Files) is read-only, so a frozen build logs into the user data dir; from
# source the project-root ``logs/`` keeps the dev workflow unchanged.
LOGS_DIR: Path = (USER_DATA_DIR / "logs") if _is_frozen() else (PROJECT_ROOT / "logs")


@dataclass(frozen=True)
class Config:
    """Immutable application chrome constants."""

    app_name: str = "Stutterbox"
    accent_hex: str = "#ffb454"  # forensic amber, per the charter
    window_width: int = 1280
    window_height: int = 800
    version: str = APP_VERSION


@dataclass
class Settings:
    """Mutable user state, persisted to ``settings.json`` via atomic write.

    ``recordings_dir`` is the allowed root for save/open. Capture parameters
    are kept here so a session is reproducible from the recording's ``meta``.
    """

    recordings_dir: str = str(DEFAULT_RECORDINGS_DIR)
    monitor: int = 1
    interval_ms: int = 250
    diff_threshold: int = 12
    tile_size: int = 48
    capture_format: str = "png"
    exclude_regions: list[list[int]] = field(default_factory=list)
    openai_api_key: str = ""

    @property
    def recordings_root(self) -> Path:
        return Path(self.recordings_dir)

    def exclude_as_regions(self) -> list[Region]:
        return [
            Region(r[0], r[1], r[2], r[3])
            for r in self.exclude_regions
            if len(r) == 4
        ]

    def set_exclude_regions(self, regions: list[Region]) -> None:
        self.exclude_regions = [[r.x, r.y, r.w, r.h] for r in regions]

    @classmethod
    def _from_mapping(cls, data: dict[str, Any]) -> "Settings":
        defaults = cls()

        def _integer(key: str, minimum: int, maximum: int, default: int) -> int:
            value = data.get(key)
            if type(value) is int and minimum <= value <= maximum:
                return value
            return default

        recordings_dir = data.get("recordings_dir")
        if (
            not isinstance(recordings_dir, str)
            or not recordings_dir.strip()
            or "\x00" in recordings_dir
            or len(recordings_dir) > 4096
        ):
            recordings_dir = defaults.recordings_dir

        capture_format = data.get("capture_format")
        if capture_format != "png":
            capture_format = defaults.capture_format

        openai_api_key = data.get("openai_api_key")
        if (
            not isinstance(openai_api_key, str)
            or len(openai_api_key) > 512
            or any(ord(char) < 32 for char in openai_api_key)
        ):
            openai_api_key = defaults.openai_api_key

        return cls(
            recordings_dir=recordings_dir,
            monitor=_integer("monitor", 0, 64, defaults.monitor),
            interval_ms=_integer("interval_ms", 50, 60_000, defaults.interval_ms),
            diff_threshold=_integer(
                "diff_threshold", 0, 255, defaults.diff_threshold
            ),
            tile_size=_integer("tile_size", 8, 1024, defaults.tile_size),
            capture_format=capture_format,
            exclude_regions=_normalize_exclude_regions(data.get("exclude_regions")),
            openai_api_key=openai_api_key,
        )


def _normalize_exclude_regions(value: object) -> list[list[int]]:
    if not isinstance(value, list):
        return []

    normalized: list[list[int]] = []
    for item in value:
        if len(normalized) >= MAX_EXCLUDE_REGIONS:
            break
        if not isinstance(item, list) or len(item) != 4:
            continue
        if any(type(part) is not int for part in item):
            continue
        x, y, width, height = item
        if not (
            0 <= x <= MAX_SETTING_COORDINATE
            and 0 <= y <= MAX_SETTING_COORDINATE
            and 0 < width <= MAX_SETTING_COORDINATE
            and 0 < height <= MAX_SETTING_COORDINATE
        ):
            continue
        normalized.append([x, y, width, height])
    return normalized


def load_settings(path: Path = SETTINGS_PATH) -> Settings:
    """Load settings, writing defaults atomically on first run."""
    path = Path(path)
    if not path.exists():
        settings = Settings()
        save_settings(settings, path)
        return settings
    try:
        raw = None if path.stat().st_size > MAX_SETTINGS_BYTES else read_json(path)
    except (JSONDecodeError, UnicodeError, RecursionError):
        raw = None
    if not isinstance(raw, dict):
        settings = Settings()
        save_settings(settings, path)
        return settings
    mapping = {key: value for key, value in raw.items() if isinstance(key, str)}
    settings = Settings._from_mapping(mapping)
    known = {f.name for f in fields(Settings)}
    filtered = {key: value for key, value in mapping.items() if key in known}
    if filtered != asdict(settings):
        save_settings(settings, path)
    return settings


def save_settings(settings: Settings, path: Path = SETTINGS_PATH) -> None:
    atomic_write_json(path, asdict(settings))
