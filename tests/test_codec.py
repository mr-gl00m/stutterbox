from __future__ import annotations

import numpy as np
import pytest

from core.codec import decode_region, encode_region
from core.errors import CorruptRecordingError
from core.model import Frame


def _patch(width: int = 40, height: int = 30) -> Frame:
    rng = np.arange(width * height * 3, dtype=np.uint8).reshape(height, width, 3)
    return rng


def test_encode_decode_roundtrip_is_lossless() -> None:
    patch = _patch()
    decoded = decode_region(encode_region(patch))
    assert np.array_equal(decoded, patch)


def test_encode_rejects_non_rgb() -> None:
    bad = np.zeros((10, 10), dtype=np.uint8)
    with pytest.raises(ValueError):
        encode_region(bad)


def test_decode_rejects_non_image() -> None:
    with pytest.raises(CorruptRecordingError):
        decode_region(b"this is not a PNG")


def test_decode_enforces_pixel_cap() -> None:
    blob = encode_region(_patch(40, 30))  # 1200 pixels
    with pytest.raises(CorruptRecordingError):
        decode_region(blob, max_pixels=100)
