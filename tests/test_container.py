from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from conftest import low_motion_frames, record_frames
from core.codec import encode_region
from core.container import RecordingReader, RecordingWriter, SCHEMA_VERSION
from core.errors import CorruptRecordingError
from core.model import RecordingMeta, Region

WIDTH, HEIGHT = 160, 120


def _meta() -> RecordingMeta:
    return RecordingMeta(
        schema_version=SCHEMA_VERSION,
        app_version="0.1.0",
        created_ms=1_700_000_000_000,
        width=WIDTH,
        height=HEIGHT,
        monitor=1,
        interval_ms=250,
        diff_threshold=12,
        tile_size=16,
        capture_format="png",
    )


def _write_minimal(path: Path) -> None:
    writer = RecordingWriter(path)
    writer.write_meta(_meta())
    full = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    writer.append_frame(0, "keyframe", Region(0, 0, WIDTH, HEIGHT), encode_region(full))
    patch = np.full((16, 16, 3), 200, dtype=np.uint8)
    writer.append_frame(100, "delta", Region(0, 0, 16, 16), encode_region(patch))
    writer.finalize()


def test_writer_reader_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "rec.stut"
    _write_minimal(path)
    with RecordingReader(path) as reader:
        assert reader.meta.width == WIDTH
        assert reader.frame_count == 2
        assert len(reader.events) == 2
        assert reader.events[0].is_keyframe


def test_finalized_file_is_single_file(tmp_path: Path) -> None:
    path = tmp_path / "rec.stut"
    _write_minimal(path)
    assert path.exists()
    assert not (tmp_path / "rec.stut-wal").exists()
    assert not (tmp_path / "rec.stut-shm").exists()


def test_chain_verifies_clean(tmp_path: Path) -> None:
    path, _ = record_frames(
        tmp_path, low_motion_frames(WIDTH, HEIGHT, 8), width=WIDTH, height=HEIGHT
    )
    with RecordingReader(path, verify=True) as reader:
        reader.verify_chain()  # explicit re-verify


def test_reader_keeps_verified_snapshot_during_concurrent_write(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.stut"
    _write_minimal(path)
    setup = sqlite3.connect(str(path))
    try:
        mode = setup.execute("PRAGMA journal_mode=WAL").fetchone()
        assert mode is not None and mode[0] == "wal"
    finally:
        setup.close()

    with RecordingReader(path, verify=True) as reader:
        verified = reader.reconstruct(1)
        attacker = sqlite3.connect(str(path), timeout=0.1)
        try:
            changed = encode_region(np.full((16, 16, 3), 7, dtype=np.uint8))
            attacker.execute(
                "UPDATE frames SET blob = ? WHERE id = 2",
                (sqlite3.Binary(changed),),
            )
            attacker.commit()
        finally:
            attacker.close()

        assert np.array_equal(reader.reconstruct(1), verified)


def test_tampered_blob_breaks_chain(tmp_path: Path) -> None:
    path = tmp_path / "rec.stut"
    _write_minimal(path)
    conn = sqlite3.connect(str(path))
    try:
        tampered = encode_region(np.full((16, 16, 3), 7, dtype=np.uint8))
        conn.execute(
            "UPDATE frames SET blob = ? WHERE id = 2", (sqlite3.Binary(tampered),)
        )
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(CorruptRecordingError):
        RecordingReader(path, verify=True)


def test_partial_initial_keyframe_rejected(tmp_path: Path) -> None:
    path = tmp_path / "partial-keyframe.stut"
    writer = RecordingWriter(path)
    writer.write_meta(_meta())
    patch = np.full((16, 16, 3), 200, dtype=np.uint8)
    writer.append_frame(0, "keyframe", Region(8, 8, 16, 16), encode_region(patch))
    writer.finalize()

    with pytest.raises(
        CorruptRecordingError, match="full-screen keyframe"
    ):
        RecordingReader(path, verify=True)


def test_partial_later_keyframe_rejected(tmp_path: Path) -> None:
    # The recorder only ever emits one keyframe (the first, full-screen). A
    # later partial keyframe is anomalous: reconstruct() starts painting from
    # the newest keyframe <= the target, so a partial one drops every pixel it
    # does not cover to black while the hash chain still verifies.
    path = tmp_path / "later-keyframe.stut"
    writer = RecordingWriter(path)
    writer.write_meta(_meta())
    full = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    writer.append_frame(0, "keyframe", Region(0, 0, WIDTH, HEIGHT), encode_region(full))
    writer.append_frame(
        100, "delta", Region(0, 0, 16, 16),
        encode_region(np.full((16, 16, 3), 200, dtype=np.uint8)),
    )
    writer.append_frame(
        200, "keyframe", Region(8, 8, 16, 16),
        encode_region(np.full((16, 16, 3), 50, dtype=np.uint8)),
    )
    writer.finalize()

    with pytest.raises(CorruptRecordingError, match="keyframe"):
        RecordingReader(path, verify=True)


def test_negative_timestamp_rejected(tmp_path: Path) -> None:
    # ts_ms has no schema CHECK. A tampered negative timestamp used to reach
    # frame_digest's ts_ms.to_bytes(..., signed=False) and raise an uncaught
    # OverflowError instead of a clean CorruptRecordingError on open.
    path = tmp_path / "neg-ts.stut"
    _write_minimal(path)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("UPDATE frames SET ts_ms = -1 WHERE id = 1")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(CorruptRecordingError):
        RecordingReader(path, verify=True)


def test_negative_coordinate_from_lax_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "negative-coordinate.stut"
    _write_minimal(path)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA ignore_check_constraints=ON")
        conn.execute("UPDATE frames SET x = -1 WHERE id = 2")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(CorruptRecordingError, match="negative coordinate"):
        RecordingReader(path, verify=True)


def test_non_blob_frame_value_is_rejected_before_decode(tmp_path: Path) -> None:
    path = tmp_path / "non-blob.stut"
    _write_minimal(path)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("UPDATE frames SET blob = 7 WHERE id = 2")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(CorruptRecordingError, match="blob has an invalid type"):
        RecordingReader(path, verify=True)


def test_extreme_recording_duration_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "extreme-duration.stut"
    writer = RecordingWriter(path)
    writer.write_meta(_meta())
    full = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    writer.append_frame(0, "keyframe", Region(0, 0, WIDTH, HEIGHT), encode_region(full))
    writer.append_frame(
        2_678_400_001,
        "delta",
        Region(0, 0, 16, 16),
        encode_region(np.zeros((16, 16, 3), dtype=np.uint8)),
    )
    writer.finalize()

    with pytest.raises(CorruptRecordingError, match="duration"):
        RecordingReader(path, verify=True)


def test_nonmonotonic_timestamps_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "nonmonotonic.stut"
    writer = RecordingWriter(path)
    writer.write_meta(_meta())
    full = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    patch = encode_region(np.zeros((16, 16, 3), dtype=np.uint8))
    writer.append_frame(0, "keyframe", Region(0, 0, WIDTH, HEIGHT), encode_region(full))
    writer.append_frame(100, "delta", Region(0, 0, 16, 16), patch)
    writer.append_frame(50, "delta", Region(0, 0, 16, 16), patch)
    writer.finalize()

    with pytest.raises(CorruptRecordingError, match="timestamp order"):
        RecordingReader(path, verify=True)


def test_unrenderable_creation_time_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "creation-time.stut"
    meta = RecordingMeta(
        schema_version=SCHEMA_VERSION,
        app_version="0.1.0",
        created_ms=10**30,
        width=WIDTH,
        height=HEIGHT,
        monitor=1,
        interval_ms=250,
        diff_threshold=12,
        tile_size=16,
        capture_format="png",
    )
    writer = RecordingWriter(path)
    writer.write_meta(meta)
    full = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    writer.append_frame(0, "keyframe", Region(0, 0, WIDTH, HEIGHT), encode_region(full))
    writer.finalize()

    with pytest.raises(CorruptRecordingError, match="creation time"):
        RecordingReader(path, verify=True)


def test_frame_count_cap_is_checked_before_index_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "frame-count.stut"
    _write_minimal(path)
    monkeypatch.setattr("core.container.MAX_FRAME_COUNT", 1)

    with pytest.raises(CorruptRecordingError, match="over the 1 cap"):
        RecordingReader(path, verify=True)


def test_non_sqlite_rejected(tmp_path: Path) -> None:
    path = tmp_path / "fake.stut"
    path.write_bytes(b"definitely not a sqlite database")
    with pytest.raises(CorruptRecordingError):
        RecordingReader(path)


def test_wrong_schema_version_rejected(tmp_path: Path) -> None:
    path = tmp_path / "empty.stut"
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE x (a INTEGER)")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(CorruptRecordingError):
        RecordingReader(path)


def test_reconstruct_matches_source_frames(tmp_path: Path) -> None:
    frames = low_motion_frames(WIDTH, HEIGHT, 10)
    path, stats = record_frames(tmp_path, frames, width=WIDTH, height=HEIGHT)
    with RecordingReader(path) as reader:
        # Event 0 is the keyframe == the first captured frame.
        assert np.array_equal(reader.reconstruct(0), frames[0])
        # The final event reconstructs the final captured frame exactly.
        assert np.array_equal(reader.reconstruct(len(reader.events) - 1), frames[-1])


def test_reconstruct_out_of_range(tmp_path: Path) -> None:
    path, _ = record_frames(
        tmp_path, low_motion_frames(WIDTH, HEIGHT, 4), width=WIDTH, height=HEIGHT
    )
    with RecordingReader(path) as reader:
        with pytest.raises(IndexError):
            reader.reconstruct(9999)
