from __future__ import annotations

import numpy as np
import pytest

from core.diff import changed_regions
from core.model import Frame


def _blank(width: int = 200, height: int = 160) -> Frame:
    return np.zeros((height, width, 3), dtype=np.uint8)


def test_no_change_returns_empty() -> None:
    a = _blank()
    assert changed_regions(a, a.copy(), threshold=12, tile=16) == []


def test_single_block_one_region() -> None:
    a = _blank()
    b = a.copy()
    b[20:40, 30:60] = 255
    regions = changed_regions(a, b, threshold=12, tile=16)
    assert len(regions) == 1
    region = regions[0]
    # The region must cover the changed pixels.
    assert region.x <= 30 and region.y <= 20
    assert region.x + region.w >= 60
    assert region.y + region.h >= 40


def test_two_separate_blocks_two_regions() -> None:
    a = _blank(320, 240)
    b = a.copy()
    b[10:30, 10:30] = 255  # top-left
    b[200:230, 280:310] = 255  # bottom-right
    regions = changed_regions(a, b, threshold=12, tile=16)
    assert len(regions) == 2


def test_subthreshold_change_ignored() -> None:
    a = _blank()
    b = a.copy()
    b[20:40, 30:60] = 5  # below threshold of 12
    assert changed_regions(a, b, threshold=12, tile=16) == []


def test_shape_mismatch_raises() -> None:
    a = _blank(100, 100)
    b = _blank(100, 120)
    with pytest.raises(ValueError):
        changed_regions(a, b, threshold=12, tile=16)


def test_regions_stay_within_bounds() -> None:
    a = _blank(150, 90)  # not a multiple of tile
    b = a.copy()
    b[80:90, 140:150] = 255  # bottom-right corner, partial tile
    regions = changed_regions(a, b, threshold=12, tile=16)
    assert len(regions) == 1
    region = regions[0]
    assert region.x + region.w <= 150
    assert region.y + region.h <= 90
