# Changelog

All notable changes to this project will be documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-07-18

### Highlights

- Generate redacted GPT-5.6 bug reports or session summaries from a full recording or selected event range.
- Find active periods through a wall-clock heat map and exclude sensitive regions before capture.
- Open, record, export, and shut down against stricter input, disk, concurrency, and overwrite boundaries.

### Added

- Added an opt-in GPT-5.6 report workspace with stable frame sampling, timestamps, pre-upload redaction, visible approval, rendered Markdown, and one-click copy.
- Added an activity heat map with change-event seeking and peak active-window reporting.
- Added screenshot-based capture exclusion, minimize-to-tray controls, a persistent recording-state indicator, and branded application icons.
- Added a one-folder Windows package with a bundled 507-event sample, local quickstart, and release verification record.

### Changed

- Capture now follows a fixed monotonic schedule so configured intervals do not drift with processing time.
- The v0.1 `.stut` schema remains compatible. Existing recordings need no migration.

### Fixed

- Reject malformed keyframes, invalid timestamps, hostile row types, excessive durations, oversized recordings, and inconsistent frame data with domain errors.
- Close capture threads safely, surface worker failures, restore the sample generator, and keep module logging available in frozen builds.

### Security

- Refuse silent replacement of recordings and exports unless the user explicitly approves an existing destination.
- Stop capture at the free-disk safety floor and publish the valid partial recording.
- Pin each verified recording to one SQLite snapshot so concurrent file changes cannot bypass chain verification.
- Normalize local settings and cap frame counts, dimensions, durations, blobs, coordinates, and decoded image size before materialization.

[0.2.0]: https://github.com/mr-gl00m/stutterbox/releases/tag/v0.2.0
