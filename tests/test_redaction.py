from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from conftest import low_motion_frames, record_frames
from core.container import RecordingReader
from core.errors import ContainerError
from core.model import Region
from core.redaction import export_recording

WIDTH, HEIGHT = 160, 120


def test_export_without_redaction_copies(tmp_path: Path) -> None:
    frames = low_motion_frames(WIDTH, HEIGHT, 8)
    src_path, _ = record_frames(tmp_path, frames, width=WIDTH, height=HEIGHT)
    dst = tmp_path / "export.stut"
    with RecordingReader(src_path) as reader:
        stats = export_recording(reader, dst, redactions=[])
    assert stats.redacted_regions == 0
    with RecordingReader(dst, verify=True) as out:
        assert np.array_equal(out.reconstruct(0), frames[0])


def test_export_with_redaction_blanks_region(tmp_path: Path) -> None:
    frames = low_motion_frames(WIDTH, HEIGHT, 8)
    src_path, _ = record_frames(tmp_path, frames, width=WIDTH, height=HEIGHT)
    dst = tmp_path / "redacted.stut"
    redaction = Region(0, 0, 48, 48)
    with RecordingReader(src_path) as reader:
        stats = export_recording(reader, dst, redactions=[redaction])
    assert stats.redacted_regions >= 1

    # The exported copy must have a valid chain and a blanked corner.
    with RecordingReader(dst, verify=True) as out:
        last = out.reconstruct(len(out.events) - 1)
        assert np.all(last[0:48, 0:48] == 0)


def test_export_is_atomic_on_success(tmp_path: Path) -> None:
    frames = low_motion_frames(WIDTH, HEIGHT, 5)
    src_path, _ = record_frames(tmp_path, frames, width=WIDTH, height=HEIGHT)
    dst = tmp_path / "out.stut"
    with RecordingReader(src_path) as reader:
        export_recording(reader, dst, redactions=[])
    assert dst.exists()
    # No leftover temp files in the destination directory.
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".out.stut")]
    assert leftovers == []


def test_export_refuses_existing_destination_by_default(tmp_path: Path) -> None:
    frames = low_motion_frames(WIDTH, HEIGHT, 3)
    src_path, _ = record_frames(tmp_path, frames, width=WIDTH, height=HEIGHT)
    dst = tmp_path / "existing.stut"
    original = b"existing recording bytes"
    dst.write_bytes(original)

    with RecordingReader(src_path) as reader:
        with pytest.raises(ContainerError, match="already exists"):
            export_recording(reader, dst, redactions=[])

    assert dst.read_bytes() == original


def test_export_can_replace_after_explicit_opt_in(tmp_path: Path) -> None:
    frames = low_motion_frames(WIDTH, HEIGHT, 3)
    src_path, _ = record_frames(tmp_path, frames, width=WIDTH, height=HEIGHT)
    dst = tmp_path / "existing.stut"
    dst.write_bytes(b"existing recording bytes")

    with RecordingReader(src_path) as reader:
        export_recording(reader, dst, redactions=[], overwrite=True)

    with RecordingReader(dst) as exported:
        assert exported.frame_count > 0
