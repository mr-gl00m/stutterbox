# Stutterbox: Project Doc

**Created:** 2026-06-02
**Status:** v0.2.0 release candidate; local report pipeline and UI complete.
Open items: one approved live GPT-5.6 call and public demo video.
**Charter:** ./PROJECT_CHARTER.md
**Checklist:** ./checklist.txt

## What it is

A local PySide6 screen recorder that does not record video the normal way. Instead of storing every frame, it captures the screen at an interval, computes which regions actually changed, and stores only those changed regions plus their timestamps into a single recording container. A three-hour low-motion session, coding, debugging, reading, becomes a small file. On playback you do not scrub by seconds; you scrub by change-event, jumping straight to the moment something on screen actually changed. Bug-repro recordings stop being 4GB blobs nobody rewatches and become forensically navigable.

## What it does

- Captures the screen at an interval and computes changed regions against the prior frame.
- Stores a keyframe plus per-event delta regions and timestamps into a SQLite recording container.
- Finalizes a recording atomically so a crash never leaves a half-written file looking complete.
- Opens a recording and reconstructs any full frame from the keyframe and the deltas up to that point.
- Presents a change-event timeline and "next change / previous change" navigation instead of a uniform seconds bar.
- Excludes chosen screen regions from capture and runs a redaction pass before any export.
- Hash-links every frame so a recording is tamper-evident.
- Selects a full session or event range for an opt-in GPT-5.6 report.
- Applies user-marked redactions before report images are encoded or uploaded.
- Renders bug reproduction steps or a session summary as copyable Markdown.

## How it will be built

The ladder has six phases. Each phase names a one-sentence goal and the concrete outputs that prove it is done. Libraries, file layout, and code structure are deferred to the scaffold skill.

### Phase 0: Scaffold
**Goal:** Empty PySide6 app with dark theme, `#ffb454` accent, and atomic settings load/save working.
**Outputs:**
- Runnable `app.py` showing an empty dark main window.
- `~/.proj_stutterbox/settings.json` created on first run via atomic write.
- Rotating-handler logging wired to `logs/stutterbox.log`.

### Phase 1: Capture and perceptual-diff core
**Goal:** A capture loop produces a small recording from only the changed regions.
**Outputs:**
- Capture loop grabbing the screen at an interval and writing to a temp container.
- Perceptual diff producing bounded changed-region bounding boxes against the prior frame.
- A finalized `.stut` recording on clean stop.
- A measured size win versus equivalent raw frames on a low-motion session. Baseline is uncompressed `width x height x 3` per tick, the floor for naive full-frame capture, not a video codec (H.264 would narrow the gap).

### Phase 2: Player and change-event scrubber
**Goal:** Open a recording and jump straight to a change, ship criterion met.
**Outputs:**
- Open a `.stut` file.
- Reconstruct any full frame from keyframe plus deltas.
- A timeline showing change events rather than uniform seconds.
- "Next change / previous change" navigation that lands on the moment something changed.

### Phase 3: Hardening and privacy
**Goal:** Untrusted recordings load safely and secrets do not leak on export.
**Outputs:**
- Container validation rejecting malformed, oversized, decompression-bomb, or path-traversal recordings with a visible reason.
- Region-exclude so chosen screen areas are never captured.
- Per-frame `prev_hash` chain verified on open.
- Export dialog with a redaction pass and an explicit confirm before any file leaves the recordings directory.

### Phase 4: Ship
**Goal:** Documented and tagged release with a sample artifact.
**Outputs:**
- `README.md` written via the `github-readme` skill.
- `v0.1.0` tag on the local repo.
- A committed sample `.stut` plus its size-versus-raw comparison.

### Phase 5: Build Week report path
**Goal:** Turn a privacy-filtered event range into a useful GPT-5.6 Markdown report.
**Outputs:**
- Inclusive event-range selection with stable, evenly spaced sampling.
- Local redaction before PNG and Base64 serialization.
- Responses API request fixed to `gpt-5.6`, with bounded output and timeout.
- Explicit per-request cloud approval and a key saved outside the repository.
- Rendered Markdown with one-click copy.
- Deterministic tests for extraction, timestamps, prompt assembly, redaction ordering, response parsing, and missing-key failure.

## Ship criterion

Record a multi-minute session, open it, jump to a known change, then generate a redacted report from a chosen range. The recording stays dramatically smaller than equivalent raw frames.
