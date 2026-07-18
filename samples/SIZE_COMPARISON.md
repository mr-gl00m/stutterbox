# Sample recording: size versus raw frames

`sample_coding_session.stut` is a synthetic three-minute low-motion session: a
mostly static editor with a blinking caret, sparse typing, and occasional
scrolls. It is generated deterministically by `generate_sample.py`, so the
numbers below reproduce exactly. The sample is synthetic on purpose, a
shippable artifact must not carry real screen pixels.

| Measure | Value |
| --- | --- |
| Resolution | 1280 x 720 |
| Duration | 180 s simulated (720 ticks at 250 ms) |
| Change events | 507 |
| Frames stored | 509 (1 keyframe + 508 delta regions) |
| Recording size | 278,528 bytes (272 KiB) |
| Raw-frame equivalent | 1,990,656,000 bytes (1.85 GiB) |
| Ratio | 0.0140 % |
| Reduction | ~7,147x smaller |

"Raw-frame equivalent" is every captured tick stored uncompressed at
`width x height x 3` bytes, the floor for naive full-frame capture, before any
video codec. The win comes from storing only the changed regions plus a hash
linked timestamp, not from a codec.

Reproduce:

```
uv run python samples/generate_sample.py
```

Open and scrub it in the app:

```
uv run python main.py
# Open -> samples/sample_coding_session.stut, then Next change / Previous change
```
