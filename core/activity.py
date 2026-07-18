from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

# Band resolution. Heat-map columns map one-to-one onto buckets, so this also
# caps horizontal detail: 240 keeps ~5px columns on a 1280px window while
# staying cheap to bin even for a multi-hour recording.
DEFAULT_BUCKETS: int = 240

# A cell counts toward the "active hours" peak window when its weight is at
# least this fraction of the hottest cell.
_PEAK_THRESHOLD: float = 0.5

# The peak window is searched at a coarse fixed resolution, independent of the
# visual band, so a single outlier bucket on a short clip can't collapse the
# readout to a sliver. On a multi-hour session this is a few-minute grid.
_PEAK_BUCKETS: int = 48

# Below this duration, wall-clock labels carry seconds; above it, HH:MM reads
# as "active hours" without clutter.
_SECONDS_LABEL_BELOW_MS: int = 120_000


@dataclass(frozen=True)
class ActivityBucket:
    """One time slice of the recording and how much changed inside it.

    Offsets are milliseconds from the recording start. ``weight`` is the raw
    summed changed-pixel area; ``intensity`` is that weight normalized against
    the hottest bucket, in ``[0, 1]``.
    """

    start_offset_ms: int
    end_offset_ms: int
    weight: float
    intensity: float


@dataclass(frozen=True)
class ActivityProfile:
    """A binned view of when a recording was busy, on a wall-clock axis."""

    created_ms: int
    duration_ms: int
    buckets: list[ActivityBucket]
    total_weight: float
    peak_start_offset_ms: int
    peak_end_offset_ms: int
    peak_fraction: float

    @property
    def is_empty(self) -> bool:
        return self.total_weight <= 0.0

    def wall_clock_ms(self, offset_ms: int) -> int:
        return self.created_ms + offset_ms

    def fmt_clock(self, offset_ms: int) -> str:
        fmt = "%H:%M" if self.duration_ms >= _SECONDS_LABEL_BELOW_MS else "%H:%M:%S"
        return datetime.fromtimestamp(self.wall_clock_ms(offset_ms) / 1000.0).strftime(fmt)

    def peak_window_label(self) -> str:
        if self.is_empty:
            return "no activity"
        start = self.fmt_clock(self.peak_start_offset_ms)
        end = self.fmt_clock(self.peak_end_offset_ms)
        pct = round(self.peak_fraction * 100)
        return f"peak {start}–{end} · {pct}% of change"


def build_profile(
    samples: Sequence[tuple[int, float]],
    *,
    created_ms: int,
    duration_ms: int | None = None,
    bucket_count: int = DEFAULT_BUCKETS,
) -> ActivityProfile:
    """Bin weighted change samples into a wall-clock activity profile.

    ``samples`` is one ``(offset_ms, weight)`` pair per changed region — the
    keyframe must be excluded by the caller, since its full-screen area would
    drown every real change. ``weight`` is changed-pixel area.
    """
    bucket_count = max(1, bucket_count)
    if duration_ms is None:
        duration = max((offset for offset, _ in samples), default=0)
    else:
        duration = duration_ms
    duration = max(0, duration)

    if not samples:
        return ActivityProfile(
            created_ms=created_ms,
            duration_ms=duration,
            buckets=[ActivityBucket(0, duration, 0.0, 0.0)],
            total_weight=0.0,
            peak_start_offset_ms=0,
            peak_end_offset_ms=duration,
            peak_fraction=0.0,
        )

    # +1 so a sample sitting exactly on the final offset lands in the last
    # bucket rather than spilling past the end.
    span = duration + 1
    weights = _bin(samples, span, bucket_count)

    peak = max(weights)
    total = math.fsum(weights)
    buckets: list[ActivityBucket] = []
    for i, weight in enumerate(weights):
        start = (i * span) // bucket_count
        end = min(((i + 1) * span) // bucket_count, duration)
        intensity = (weight / peak) if peak > 0 else 0.0
        buckets.append(ActivityBucket(start, end, weight, intensity))

    coarse_count = min(bucket_count, _PEAK_BUCKETS)
    coarse = weights if coarse_count == bucket_count else _bin(samples, span, coarse_count)
    peak_start, peak_end, peak_fraction = _peak_window(
        coarse, span, coarse_count, total, duration
    )
    return ActivityProfile(
        created_ms=created_ms,
        duration_ms=duration,
        buckets=buckets,
        total_weight=total,
        peak_start_offset_ms=peak_start,
        peak_end_offset_ms=peak_end,
        peak_fraction=peak_fraction,
    )


def _bin(samples: Sequence[tuple[int, float]], span: int, count: int) -> list[float]:
    """Sum sample weights into ``count`` equal time slices across ``span``."""
    weights = [0.0] * count
    for offset, weight in samples:
        if weight <= 0:
            continue
        idx = (max(0, offset) * count) // span
        if idx >= count:
            idx = count - 1
        weights[idx] += weight
    return weights


def _peak_window(
    weights: list[float], span: int, count: int, total: float, duration: int
) -> tuple[int, int, float]:
    """Find the heaviest contiguous run of cells at least half as hot as peak.

    Returns its start/end offsets and the fraction of total change it holds —
    the "you were most active from X to Y" window.
    """
    peak = max(weights) if weights else 0.0
    if peak <= 0 or total <= 0:
        return 0, duration, 0.0

    threshold = peak * _PEAK_THRESHOLD
    best_sum = -1.0
    best_start = 0
    best_end = duration
    run_start: int | None = None
    run_sum = 0.0
    for i, weight in enumerate(weights):
        if weight >= threshold and weight > 0:
            if run_start is None:
                run_start = i
                run_sum = 0.0
            run_sum += weight
            if run_sum > best_sum:
                best_sum = run_sum
                best_start = (run_start * span) // count
                best_end = min(((i + 1) * span) // count, duration)
        else:
            run_start = None
            run_sum = 0.0

    return best_start, best_end, (best_sum / total if best_sum > 0 else 0.0)
