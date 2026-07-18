# Stutterbox v0.2.0 release verification

Date: 2026-07-18

Status: release candidate with one live API gate open.

## Automated gates

- `uv lock --check`: clean.
- `uv sync --frozen`: clean.
- `uv run python -m pytest`: 78 passed.
- `uv run python -m mypy --strict`: clean across 44 source files.
- `git diff --check`: clean before the release commit.

## Bundled sample

- Recording: `samples/sample_coding_session.stut`
- Resolution: 1280x720
- Change events: 507
- Selected report frames: 8
- Local preparation time: 0.211 seconds
- PNG bytes before Base64: 39,107
- Hash chain: verified on open

The report preparation run used the full event range and an empty redaction list. The redaction stage still ran on every reconstructed frame.

## Windows package

- Artifact: `dist/Stutterbox-v0.2.0-win64.zip`
- Size: 66,054,886 bytes
- SHA-256: `5B68412FDE152650CB485D1CEE4543EAFE7F29B7ACABF845F387BC8DF8897756`
- ZIP entries: 288
- Required entries present: `Stutterbox.exe`, `READ-ME-FIRST.txt`, `sample_coding_session.stut`, `LICENSE.txt`, `THIRD_PARTY_NOTICES.md`, and eight license texts under `LICENSES/`
- Packaged sample hash matches the source sample.
- Packaged executable stayed running through a three-second hidden startup smoke test.

PyInstaller reported platform-conditional and optional imports only. The frozen app reached its Qt event loop during the smoke test.

## Open gate

No OpenAI key was present in the environment or local settings during this pass. One approved GPT-5.6 call against the bundled sample remains required before the final v0.2.0 tag.
