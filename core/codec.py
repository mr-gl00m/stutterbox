from __future__ import annotations

import io

import numpy as np
from PIL import Image

from core.errors import CorruptRecordingError
from core.model import Frame

# Hard ceiling on any single decoded region. A 4K screen is ~8.3M pixels; a
# generous cap leaves room for multi-monitor keyframes while refusing
# decompression-bomb blobs that claim absurd dimensions.
MAX_REGION_PIXELS: int = 64_000_000

# Pillow's own global bomb guard. Set above MAX_REGION_PIXELS so our explicit
# check is the one that fires with a useful reason, not Pillow's Decompression
# bombWarning/Error.
Image.MAX_IMAGE_PIXELS = MAX_REGION_PIXELS + 1


def encode_region(frame: Frame) -> bytes:
    """Encode an RGB region to PNG bytes.

    PNG is lossless, so a reconstructed frame is pixel-identical to capture —
    a requirement for tamper-evident bug-repro recordings.
    """
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError(f"expected (h, w, 3) RGB frame, got shape {frame.shape!r}")
    img = Image.fromarray(np.ascontiguousarray(frame), mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=6)
    return buf.getvalue()


def decode_region(blob: bytes, *, max_pixels: int = MAX_REGION_PIXELS) -> Frame:
    """Decode PNG bytes to an RGB frame, refusing decompression bombs.

    The declared image dimensions are checked from the header before the
    pixels are materialized, so an attacker-controlled blob cannot force a
    huge allocation.
    """
    try:
        img = Image.open(io.BytesIO(blob))
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise CorruptRecordingError(f"frame blob is not a decodable image: {exc}") from exc

    width, height = img.size
    if width <= 0 or height <= 0:
        raise CorruptRecordingError("frame blob has non-positive dimensions")
    if width * height > max_pixels:
        raise CorruptRecordingError(
            f"frame blob declares {width}x{height} pixels, over the {max_pixels} cap"
        )

    try:
        rgb = img.convert("RGB")
        # np.array (not asarray) returns a writable, owned copy, detached from
        # Pillow's read-only buffer so callers can blank regions in place.
        arr = np.array(rgb, dtype=np.uint8)
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise CorruptRecordingError(f"frame blob failed to decode: {exc}") from exc

    if arr.ndim != 3 or arr.shape[2] != 3:
        raise CorruptRecordingError("decoded frame is not 3-channel RGB")
    return arr
