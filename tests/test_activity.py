from __future__ import annotations

from core.activity import ActivityBucket, build_profile


def test_empty_samples_yield_empty_profile() -> None:
    profile = build_profile([], created_ms=1_000, duration_ms=5_000)
    assert profile.is_empty
    assert profile.total_weight == 0.0
    assert profile.buckets  # always at least one bucket to render against
    assert profile.peak_window_label() == "no activity"


def test_intensity_normalized_against_peak() -> None:
    samples = [(0, 10.0), (900, 100.0)]
    profile = build_profile(samples, created_ms=0, duration_ms=1_000, bucket_count=10)

    assert max(b.intensity for b in profile.buckets) == 1.0
    hottest = max(profile.buckets, key=lambda b: b.weight)
    assert hottest.intensity == 1.0
    assert abs(profile.total_weight - 110.0) < 1e-9


def test_buckets_tile_the_duration_without_gaps() -> None:
    profile = build_profile(
        [(0, 1.0), (500, 1.0)], created_ms=0, duration_ms=1_000, bucket_count=8
    )
    assert profile.buckets[0].start_offset_ms == 0
    assert profile.buckets[-1].end_offset_ms == 1_000
    for earlier, later in zip(profile.buckets, profile.buckets[1:]):
        assert earlier.end_offset_ms == later.start_offset_ms


def test_peak_window_lands_on_the_dense_block() -> None:
    samples: list[tuple[int, float]] = [(t, 1.0) for t in range(0, 200, 50)]
    samples += [(t, 50.0) for t in range(1_000, 1_200, 10)]  # heavy cluster
    samples += [(t, 1.0) for t in range(2_000, 2_200, 50)]

    profile = build_profile(samples, created_ms=0, duration_ms=2_200, bucket_count=22)

    assert profile.peak_start_offset_ms <= 1_200
    assert profile.peak_end_offset_ms >= 1_000
    assert profile.peak_fraction > 0.5


def test_keyframe_area_excluded_by_caller_keeps_real_activity_hot() -> None:
    # Mirrors the main-window caller: drop the full-screen keyframe sample so a
    # later small change still reads as the hottest bucket.
    full_screen = 1920 * 1080
    delta_only = [(800, float(64 * 64))]
    profile = build_profile(
        delta_only, created_ms=0, duration_ms=1_000, bucket_count=10
    )
    hottest = max(profile.buckets, key=lambda b: b.weight)
    assert hottest.weight == float(64 * 64)
    assert hottest.weight < full_screen  # sanity: the delta is the small one


def test_wall_clock_offset_maps_through_created_ms() -> None:
    profile = build_profile([(0, 1.0)], created_ms=1_700_000_000_000, duration_ms=0)
    assert profile.wall_clock_ms(0) == 1_700_000_000_000


def test_bucket_is_immutable() -> None:
    bucket = ActivityBucket(0, 100, 5.0, 0.5)
    try:
        bucket.weight = 9.0  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("ActivityBucket should be frozen")
