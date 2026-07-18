# Stutterbox: Project Charter

**Created:** 2026-06-02
**Stack:** Python 3.10+, PySide6, SQLite, mss, numpy, Pillow, and stdlib urllib for the opt-in OpenAI request
**Directory:** N:/.pending_release/proj_stutterbox
**Audience:** individuals and teams reviewing coding, debugging, support, and reading sessions
**LLM-facing:** yes, only through an explicit GPT-5.6 report action
**Prior art considered:** none found with real overlap. Grepped `N:/proj_*`, `N:/tool_*`, `N:/experiment*`, `N:/tinker*`, and `.md` files across `N:/` for screen-record / screen-capture / perceptual-diff / delta-record keywords. All hits were dependencies (playwright video-recording) or Godot engine dumps. `proj_sav_savepoint` is a file backup/snapshot tool, not a screen recorder, different artifact, different mechanism.

## 1. Purpose

Record the screen by storing only the regions that changed plus timestamps, producing a small artifact you scrub by change-event instead of by seconds.

## 2. Ship criterion

Record a multi-minute session, open it, jump to a known change, then generate a redacted Markdown report from a chosen range.

## 3. SIGIL threat model

### Layer 1: Cryptographic signing
Partial / opt-in. The recording's frame store is hash-linked (a `prev_hash` chain across keyframe and delta frames), giving tamper-evidence, a bug-repro recording can be shown un-doctored. An optional Ed25519 signature over the finished recording manifest supports "provable repro" sharing. The hash chain is required; the signature is deferred.

### Layer 2: Structural trust boundaries
The report boundary accepts verified recording frames plus user-marked rectangles. Range selection, sampling, reconstruction, redaction, and image encoding are deterministic. Model output returns as display-only Markdown and never enters capture, persistence, or command execution.

### Layer 3: Input normalization
Applies to the open-a-recording path and the cloud response. A `.stut` file from someone else is untrusted input: validate the container, cap frame counts, duration, blob size, region bounds, and decoded dimensions, and reject malformed rows with a visible reason. The report response is capped at 4 MiB, parsed as JSON, and reduced to message text.

### Layer 4: Tag breakout prevention
The report prompt is fixed application text plus numeric timestamps. Captured text remains inside image inputs. Returned Markdown is rendered as document content and has no execution path.

### Layer 5: Persona stability preamble
The model gets one constrained role: produce a bug report or session summary from visible chronological evidence.

### Layer 6: Uncertainty / consistency gates
The prompt forbids invented hidden actions, causes, and events between samples. Every uncertain claim belongs in a dedicated Uncertainties section.

### Layer 7: Tool affinity
Reports use `gpt-5.6` through the Responses API with text and image inputs. No model tools are exposed.

### Support structures
- **Audit chain:** the recording container is the chain. A `frames` table, `(id, ts_ms, kind, bbox, blob, frame_sha256, prev_hash)`, links every keyframe and delta to the prior frame. This `prev_hash` chain doubles as SIGIL's tamper-evident log and as the recording's integrity guarantee; a separate capture log is unnecessary.
- **Time-bounded ops:** N/A. Recordings are archival artifacts, not credentials.
- **Human-in-the-loop:** three gated actions. (1) Capture starts only on an explicit action and shows a visible indicator. (2) Export halts for confirmation. (3) Every GPT-5.6 report requires an API key plus per-request approval after the redaction count is shown.

## 4. Coding non-negotiables

- **Local-first:** capture, playback, export, settings, redaction, and report preparation run locally. Only `core/report.py` can make an outbound request, after explicit approval, to one fixed OpenAI endpoint.
- **Atomic writes:** `core/io.py::atomic_write_json` for settings; a recording is captured to a temp container and published to its final `.stut` only on a clean stop. Publication refuses to replace an existing recording.
- **SQLite hygiene:** WAL, `foreign_keys = ON`, parameterized queries only, numbered migrations for the container schema in `migrations/`.
- **Type hints:** `from __future__ import annotations` in every file, `Path` from `pathlib`, `mypy --strict` clean.
- **Logging:** `RotatingFileHandler` 5MB × 3 at `logs/stutterbox.log`, `sys.excepthook` wired. Never log captured pixels, API keys, request payloads, or report text.
- **Never bare `except`:** named exceptions (`CaptureError`, `ContainerError`, `CorruptRecordingError`).
- **Secrets discipline:** recordings may contain passwords, tokens, or PII. The API key lives in user settings outside the repository. Report images are redacted before serialization. There is no telemetry.
- **Path traversal / SSRF:** recording save paths are validated against their allowed root. The report URL is a fixed constant with no user-controlled host or path.
- **No prohibited deps:** no ORM, web framework, cloud SDK, telemetry, or Electron. The optional report boundary uses stdlib urllib.
- **Conventional commits:** yes.

Sometimes-applies:
- **Integration tests against real SQLite:** yes, a capture → container → reopen → frame-reconstruction round-trip, plus an audit-chain continuity test.
- **Dockerized dev environment:** no.
- **Signed release artifacts:** deferred past v0.2.0.

## 5. UI & aesthetics

Dark theme, accent forensic amber `#ffb454`. The primary driver is the change-event timeline plus recording controls. Report generation ends in a rendered Markdown view with one copy button. Typed labels include "Record", "Stop", "Next change", "Export", and "Generate report".

## 6. Voice & prose rules

Applies to commit messages, UI strings, docs, and the README. No em dashes or en dashes. Commit messages stay under 72 characters with a conventional-commits prefix.

## 7. Prohibited dependencies

SQLAlchemy, Peewee, Django ORM, Prisma, TypeORM; Flask, FastAPI, Django, Express; Electron; boto3, google-cloud-*, firebase-admin; sentry-sdk, opentelemetry-*, Segment; arbitrary network destinations; any paid or subscription dev tool.

## 8. License

**MIT.** Code-only dev tool with no embedded creative IP. `LICENSE` at the project root, copyright line `Copyright (c) 2026 Cid`. The scaffold skill writes it atomically during Phase 0.

## 9. Handoff

Charter frozen. Proj doc and checklist committed alongside. Next step: `pyside6-dark-scaffold` with accent `#ffb454`, primary driver the change-event timeline scrubber and recording controls.
