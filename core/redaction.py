from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.codec import decode_region, encode_region
from core.container import RecordingReader, RecordingWriter, WriterStats
from core.errors import ContainerError
from core.io import atomic_publish_file
from core.model import Frame, Region


@dataclass(frozen=True)
class ExportStats:
    path: Path
    frame_count: int
    blob_bytes: int
    redacted_regions: int


def _blank_redactions(patch: Frame, frame_rect: Region, redactions: list[Region]) -> bool:
    """Zero out any part of ``patch`` covered by a redaction. Returns hit flag."""
    touched = False
    for redaction in redactions:
        inter = frame_rect.intersection(redaction)
        if inter is None:
            continue
        local_x = inter.x - frame_rect.x
        local_y = inter.y - frame_rect.y
        patch[local_y : local_y + inter.h, local_x : local_x + inter.w] = 0
        touched = True
    return touched


def redact_frame(frame: Frame, redactions: list[Region]) -> Frame:
    """Return a full-frame copy with every marked region blanked."""
    redacted = np.ascontiguousarray(frame.copy())
    height, width = redacted.shape[:2]
    _blank_redactions(redacted, Region(0, 0, width, height), redactions)
    return redacted


def export_recording(
    reader: RecordingReader,
    dst_path: Path,
    *,
    redactions: list[Region] | None = None,
    overwrite: bool = False,
) -> ExportStats:
    """Write a copy of the recording to ``dst_path``, redactions applied.

    Each frame's blanked regions are baked into a re-encoded blob, and the
    copy gets a fresh, valid hash chain. A temp file in the destination
    directory is published atomically only on success.
    """
    redactions = list(redactions or [])
    dst_path = Path(dst_path)
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_str = tempfile.mkstemp(
        dir=str(dst_path.parent), prefix=f".{dst_path.name}.", suffix=".tmp"
    )
    os.close(fd)
    tmp_path = Path(tmp_str)

    writer = RecordingWriter(tmp_path)
    redacted_hits = 0
    try:
        writer.write_meta(reader.meta)
        for row, blob in reader.iter_frames():
            patch = decode_region(blob)
            frame_rect = row.region
            if _blank_redactions(patch, frame_rect, redactions):
                redacted_hits += 1
                new_blob = encode_region(np.ascontiguousarray(patch))
            else:
                new_blob = blob
            writer.append_frame(row.ts_ms, row.kind, frame_rect, new_blob)
        stats: WriterStats = writer.finalize()
        try:
            atomic_publish_file(tmp_path, dst_path, overwrite=overwrite)
        except FileExistsError as exc:
            raise ContainerError(f"export destination already exists: {dst_path}") from exc
        except OSError as exc:
            raise ContainerError(f"could not publish export: {exc}") from exc
    except BaseException:
        writer.close()
        tmp_path.unlink(missing_ok=True)
        raise

    return ExportStats(
        path=dst_path,
        frame_count=stats.frame_count,
        blob_bytes=stats.blob_bytes,
        redacted_regions=redacted_hits,
    )
