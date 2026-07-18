# Stutterbox v0.1.0 release-confidence pass

Date: 2026-07-04
Branch: `weekend-2026-07-04`

Purpose: raise confidence in an already-built v0.1.0 by auditing correctness,
validating the sample, and confirming the shipped docs match behavior. This is
the record of that pass, not a shipping decision. The tag and any release
action stay with a human.

## Automated gates

- `uv run pytest`: 59 passed (57 at baseline, plus two regression tests added
  for the bugs below).
- `uv run mypy --strict`: clean, 42 source files.

## Sample validation

`samples/sample_coding_session.stut` opens, `verify_chain()` passes, and
reconstruct of the first and last event returns `(720, 1280, 3)` frames.

| Measure | Value | Matches doc |
| --- | --- | --- |
| Size | 278,528 bytes | README, SIZE_COMPARISON.md |
| Frames | 509 (1 keyframe + 508 deltas) | SIZE_COMPARISON.md |
| Change events | 507 | SIZE_COMPARISON.md |
| Raw-frame equivalent | 1,990,656,000 bytes (1280 x 720 x 3 x 720 ticks) | SIZE_COMPARISON.md |
| Ratio | 0.0140 % | SIZE_COMPARISON.md |
| Reduction | 7,147x | README, SIZE_COMPARISON.md |

The arithmetic reproduces exactly.

## Bugs found and fixed

Full detail in `docs/bug-hunt-report.md`. Three container-reader defects, all
in the untrusted-recording open path, all closed with regression tests.

1. Partial initial keyframe accepted (medium). Prior finding BH-2026-07-03-001;
   fix and test were sitting uncommitted, folded in as `ee42307`.
2. Partial later keyframe accepted (medium). The guard now covers every
   keyframe, not just the first. Commit `897b3b7`.
3. Negative timestamp raised `OverflowError` instead of `CorruptRecordingError`
   (medium). `ts_ms < 0` is now rejected during index validation. Commit
   `897b3b7`.

## Docs confidence pass

Three claims checked against actual behavior. All three hold; no drift found.

1. Size comparison uses raw uncompressed frames, not a codec equivalent.
   `samples/SIZE_COMPARISON.md` states the baseline is "every captured tick
   stored uncompressed at width x height x 3 bytes, the floor for naive
   full-frame capture, before any video codec," and "the win comes from storing
   only the changed regions ... not from a codec." `PROJ_DOC.md` and the README
   size block say the same. Confirmed accurate.

2. Privacy claims match the export and redaction code. The README describes two
   controls: exclude regions blanked at grab time and never written
   (`core/capture.py` `blank_regions`, called on every grab), and redaction as
   an export-time pass that bakes boxes into a fresh copy with its own valid
   hash chain while the original is untouched, gated behind an explicit confirm
   (`core/redaction.py` `export_recording` plus the confirm dialog in
   `ui/main_window.py` `_on_export`). Coverage is spatial only, which the README
   does not overstate. Confirmed accurate.

3. The Ed25519 signature is clearly deferred. The README status says the
   optional Ed25519 signature "is specified but deferred past v0.1: the hash
   chain ships, the signature does not yet." `checklist.txt` lists it under
   OUT OF SCOPE, "charter-deferred to public release." Confirmed clearly marked.

Note: the shipped docs and many docstrings use em dashes, against the house
style rule. That is a pre-existing repo-wide pattern, not drift in the three
claims above, and not a correctness issue. Left for a separate style sweep.

## What remains at a human gate

- Real multi-minute display capture. Cannot be self-verified. Run the gate in
  `docs/real-display-qa.md` (full app flow, including redacted export) or the
  quick harness in `.docs/real_display_verification.md`. The checklist item
  stays `[ ]` until a human closes it.
- `v0.1.0` tag and any release action. Not taken here. Confirm the frozen
  surface (schema, settings format) and a clean tree first.
