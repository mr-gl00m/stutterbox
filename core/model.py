from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

# A full or partial screen frame: (height, width, 3) uint8 in RGB order.
Frame = NDArray[np.uint8]

FrameKind = Literal["keyframe", "delta"]


@dataclass(frozen=True)
class Region:
    """An axis-aligned screen rectangle in pixel coordinates."""

    x: int
    y: int
    w: int
    h: int

    @property
    def area(self) -> int:
        return self.w * self.h

    def clamped(self, width: int, height: int) -> "Region":
        x0 = max(0, min(self.x, width))
        y0 = max(0, min(self.y, height))
        x1 = max(0, min(self.x + self.w, width))
        y1 = max(0, min(self.y + self.h, height))
        return Region(x0, y0, x1 - x0, y1 - y0)

    def intersection(self, other: "Region") -> "Region | None":
        x0 = max(self.x, other.x)
        y0 = max(self.y, other.y)
        x1 = min(self.x + self.w, other.x + other.w)
        y1 = min(self.y + self.h, other.y + other.h)
        if x1 <= x0 or y1 <= y0:
            return None
        return Region(x0, y0, x1 - x0, y1 - y0)


@dataclass(frozen=True)
class RecordingMeta:
    """Header metadata for a recording, mirrored into the ``meta`` table."""

    schema_version: int
    app_version: str
    created_ms: int
    width: int
    height: int
    monitor: int
    interval_ms: int
    diff_threshold: int
    tile_size: int
    capture_format: str


@dataclass(frozen=True)
class ChangeEvent:
    """One capture tick that produced at least one changed region.

    ``index`` is the event ordinal used by the scrubber; ``ts_ms`` is the
    timeline position; ``last_frame_id`` is the highest frame row id in the
    event, used as the reconstruction cut-off.
    """

    index: int
    ts_ms: int
    region_count: int
    last_frame_id: int
    is_keyframe: bool
