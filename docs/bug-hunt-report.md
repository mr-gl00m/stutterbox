# Stutterbox bug-hunt report

Date: 2026-07-04
Branch: `weekend-2026-07-04`
Baseline commit: `7f8f60a`
Scope: correctness audit of the six areas named in `WEEKEND_PLAN.md`.

## Baseline (before any change)

- `uv run pytest`: 57 passed.
- `uv run mypy --strict`: clean, 42 source files.
- `samples/sample_coding_session.stut`: opens, `verify_chain()` passes, reconstruct of the first and last event returns `(720, 1280, 3)` frames. Size 278,528 bytes, 509 frames, 507 events. Matches `README.md` and `samples/SIZE_COMPARISON.md`.

A prior report (`.bugs/report_2026-07-03-155934.md`) had left one verified medium open: BH-2026-07-03-001, a partial initial keyframe accepted on open. Its fix and repro test were sitting uncommitted in the working tree. Confirmed as in-progress work for this task, committed as `ee42307`.

## What was checked

| Area | Method | Result |
| --- | --- | --- |
| Capture loop pacing | Read `core/recorder.py` run loop; re-ran `tests/test_recorder_pacing.py` | No defect. Fixed-schedule pacing (`next_due += interval`) drops backlog on a slow tick instead of burst-grabbing. Regression test green. |
| Container schema and validation | Read `core/container.py`, `migrations/001_initial.sql`; crafted tampered `.stut` files | One defect found and fixed (negative timestamp). Column/table/version/dimension guards are sound. |
| Hash-chain verification | Read `core/hashchain.py`, `RecordingReader.verify_chain` | Logic correct: genesis anchor, prev-link check before digest recompute, names the first broken frame. The negative-timestamp crash surfaced here but the root cause is missing index validation, fixed upstream of the chain walk. |
| Reconstruction correctness | Read `RecordingReader.reconstruct` and `_latest_keyframe_id`; crafted a later partial keyframe | One defect found and fixed (partial later keyframe). Normal keyframe-plus-delta reconstruction is exact, covered by roundtrip tests. |
| Export and redaction rewrite | Read `core/redaction.py`; re-ran `tests/test_redaction.py` | No defect. Redaction is spatially complete because every keyframe now must cover the full screen, so any in-bounds redaction box intersects the keyframe and every overlapping delta. Fresh chain, atomic `os.replace`. |
| Region exclusion | Read `core/capture.py` `blank_regions`; re-ran `tests/test_capture.py` | No defect. Excluded regions are zeroed on every grab (keyframe included), clamped to bounds, so an excluded area is constant black and never produces a stored delta. |

## Findings

### BH-2026-07-04-001: partial later keyframe accepted (medium, fixed)

Category: broken invariant. Location: `core/container.py` index validation and `reconstruct`.

The initial-keyframe guard from `ee42307` covered only `index[0]`. `reconstruct()` starts painting from the newest keyframe with id at or below the target event (`_latest_keyframe_id`), onto a zero-filled canvas. A recording with a later keyframe smaller than the screen therefore reconstructs to a mostly black frame for any event at or after that keyframe, while `verify_chain()` still passes. A hand-built or tampered `.stut` can drop real captured content and read as verified.

Reachability: direct. `RecordingWriter.append_frame` accepts any kind and region, so the tampered file can be produced with a valid chain. The stock recorder never emits a non-initial keyframe, so no legitimate recording is affected.

Fix: require every keyframe (not only the first) to cover `Region(0, 0, meta.width, meta.height)`. Repro: `tests/test_container.py::test_partial_later_keyframe_rejected`.

### BH-2026-07-04-002: negative timestamp raises OverflowError instead of CorruptRecordingError (medium, fixed)

Category: error path on untrusted input. Location: `core/container.py` index validation, surfacing in `core/hashchain.py:frame_digest`.

`ts_ms` has no `CHECK` in the schema. `frame_digest` encodes it with `ts_ms.to_bytes(8, "big", signed=False)`. A tampered negative `ts_ms` reached that call during `verify_chain()` and raised an uncaught `OverflowError`. The reader's contract is that untrusted input raises `CorruptRecordingError` with a visible reason; an `OverflowError` breaks that contract and could crash a caller that only guards the documented exception.

Reachability: direct, via a sqlite `UPDATE` on a stored row. The region fields cannot trigger the same overflow: the schema pins `x, y, w, h >= 0` and the reader bounds them under `MAX_DIMENSION`, well inside a 4-byte unsigned field. Only `ts_ms` was ungated, and sqlite can store it negative.

Fix: reject `ts_ms < 0` during index validation, before the chain walk. Repro: `tests/test_container.py::test_negative_timestamp_rejected`.

## Checked and left as-is

- Meta fields `interval_ms`, `tile_size`, `diff_threshold`, `monitor` are parsed as ints but not range-validated. They are written to the container and surfaced for display only; the reader and playback never divide by or allocate from them, so a zero or negative value cannot crash on open. Low severity, no change.
- Event grouping (`_build_events`) merges frames that share a `ts_ms`. Two distinct capture ticks that land in the same millisecond would collapse into one navigable event. At `interval_ms=250` this cannot happen; at sub-millisecond intervals it is a navigation nicety, not a data-loss bug. Left as-is.

## Note outside this pass

Docstrings and some doc prose across the repo use em dashes, against the house style rule. This is a pre-existing, repo-wide pattern in shipped code and docs, not a correctness issue and not drift in the three claims audited in the docs pass. Flagged for a separate style sweep rather than folded into this branch.

## Verification after fixes

- `uv run pytest`: 59 passed (57 baseline plus the two new repro tests).
- `uv run mypy --strict`: clean, 42 source files.
- `samples/sample_coding_session.stut`: still opens, `verify_chain()` passes, reconstruct of the first and last event unchanged. The sample has exactly one full-screen keyframe, so the stricter guard does not reject it.

## Commits

- `ee42307` fix(container): reject a recording whose initial keyframe is not full-screen
- `897b3b7` fix(container): reject partial later keyframes and negative timestamps
