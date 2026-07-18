from __future__ import annotations

from pathlib import Path

from core.config import Settings, load_settings, save_settings
from core.io import atomic_write_json, atomic_write_text, read_json, read_text


def test_atomic_write_text_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "note.md"
    atomic_write_text(target, "# hello\n")
    assert read_text(target) == "# hello\n"


def test_atomic_write_json_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "data.json"
    payload = {"accent": "#ffb454", "count": 3}
    atomic_write_json(target, payload)
    assert read_json(target) == payload


def test_atomic_write_creates_parent(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir" / "file.txt"
    atomic_write_text(target, "ok")
    assert target.read_text(encoding="utf-8") == "ok"


def test_settings_created_on_first_run(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    assert not path.exists()
    settings = load_settings(path)
    assert path.exists()
    assert settings.interval_ms == 250
    assert settings.exclude_regions == []


def test_settings_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = Settings(
        interval_ms=500,
        diff_threshold=20,
        tile_size=32,
        openai_api_key="sk-local-test-key",
    )
    save_settings(settings, path)
    loaded = load_settings(path)
    assert loaded.interval_ms == 500
    assert loaded.diff_threshold == 20
    assert loaded.tile_size == 32
    assert loaded.openai_api_key == "sk-local-test-key"


def test_settings_ignores_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    atomic_write_json(path, {"interval_ms": 333, "bogus": "ignored"})
    loaded = load_settings(path)
    assert loaded.interval_ms == 333


def test_settings_normalize_unsafe_types_and_ranges(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    atomic_write_json(
        path,
        {
            "recordings_dir": "",
            "monitor": True,
            "interval_ms": 0,
            "diff_threshold": -1,
            "tile_size": 1,
            "capture_format": "jpeg",
            "exclude_regions": [[0, 0, 16, 16], [0, 0, -1, 10], "bad"],
            "openai_api_key": "sk-test\ninjected",
        },
    )

    loaded = load_settings(path)

    defaults = Settings()
    assert loaded.recordings_dir == defaults.recordings_dir
    assert loaded.monitor == defaults.monitor
    assert loaded.interval_ms == defaults.interval_ms
    assert loaded.diff_threshold == defaults.diff_threshold
    assert loaded.tile_size == defaults.tile_size
    assert loaded.capture_format == defaults.capture_format
    assert loaded.exclude_regions == [[0, 0, 16, 16]]
    assert loaded.openai_api_key == ""


def test_settings_reset_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    atomic_write_text(path, "{broken json")

    loaded = load_settings(path)

    assert loaded == Settings()
    assert read_json(path) == {
        "recordings_dir": str(loaded.recordings_dir),
        "monitor": loaded.monitor,
        "interval_ms": loaded.interval_ms,
        "diff_threshold": loaded.diff_threshold,
        "tile_size": loaded.tile_size,
        "capture_format": loaded.capture_format,
        "exclude_regions": loaded.exclude_regions,
        "openai_api_key": loaded.openai_api_key,
    }
