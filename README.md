# Stutterbox

A local screen recorder that jumps by change and turns redacted sessions into reports.

<p align="center">
  <img src="https://github.com/mr-gl00m/stutterbox/blob/main/resources/icons/stutterbox.png" alt="Stutterbox icon" width="140">
</p>

```text
3-minute low-motion session, 1280x720

raw full frames      1,990,656,000 bytes   1.85 GiB
Stutterbox .stut           278,528 bytes   272 KiB
stored ratio                 0.0140 %       about 7,147x smaller

507 change events, hash chain verified on open
selected range -> 8 redacted frames -> GPT-5.6 -> Markdown report
```

## What it is

Stutterbox records screen changes into a small SQLite container and scrubs by change-event instead of by seconds. It is built for bug reproduction, coding, debugging, and reading sessions where most pixels stay still. An optional GPT-5.6 report path turns a selected event range into reproduction steps or a session summary after local redaction. The tradeoff is deliberate: high-motion video gives back the size win, and there is no audio or smooth playback.

## New for OpenAI Build Week

Stutterbox v0.1.0 shipped on June 2, 2026 with local recording, change-event playback, redaction, export, and the `.stut` hash chain. Work completed during the July 13 to 21 Build Week submission period adds:

- The deterministic report pipeline: event-range selection, stable sampling, timestamps, local redaction, GPT-5.6 request assembly, and constrained Markdown output.
- The opt-in PySide6 report workspace: API key settings, per-request upload approval, visible failures, rendered reports, and clipboard copy.
- Release hardening around hostile recordings, disk exhaustion, concurrent mutation, capture shutdown, local settings, and overwrite approval.
- A tested Windows x64 package and the bundled 507-event sample path for judges.

The public [`v0.1.0...main` comparison](https://github.com/mr-gl00m/stutterbox/compare/v0.1.0...main) preserves the complete timestamped history. The core report work is anchored by commits `ff41406` and `87a57d6`; it remains separate from the June release.

## Quickstart

The packaged v0.2.0 judge build targets Windows x64. Extract the complete ZIP, keep the `Stutterbox` folder together, and run `Stutterbox.exe`. The source path below is tested most heavily on Windows; macOS and Linux use the same `mss` capture backend with less field time.

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/). Linux capture also needs an X11 or Wayland backend available to `mss`.

```bash
git clone https://github.com/mr-gl00m/stutterbox.git
cd stutterbox
uv sync
uv run python main.py
```

To test without recording:

1. Click **Open** and choose `samples/sample_coding_session.stut`.
2. Step through the 507 events with **Next change**, the timeline, or the heat map.
3. Click **Redact** and drag over any region that must stay local.
4. Click **Generate report**, choose a full session or event range, and select a bug report or session summary.
5. Add an OpenAI API key, approve the upload for that request, then copy the rendered Markdown.

The bundled sample prepares eight redacted frames locally in about 0.21 seconds on the release machine. API latency depends on the network and account. The key is stored in `~/.proj_stutterbox/settings.json`, outside the repository. Report generation fails with a visible message when the key is absent, the network is unavailable, or OpenAI rejects the request.

Run the deterministic suite:

```bash
uv run python -m pytest
uv run python -m mypy --strict
```

## How it works

Each capture tick grabs an RGB frame through `mss`. A tile-based perceptual diff marks regions that changed beyond the configured threshold, and adjacent tiles merge into bounding boxes. The first frame is a full keyframe; later rows are lossless PNG deltas. Playback reconstructs a requested change event by painting forward from the latest full keyframe.

The `.stut` file is also the audit log. Every frame row folds its contents and the prior row hash into `frame_sha256`. Open verifies the chain plus the SQLite header, schema, row shape, frame count, duration, blob size, region bounds, and decoded image dimensions. Capture writes to a temporary WAL-backed container, folds it to one file, and publishes only after a clean stop.

Cloud reporting is isolated in `core/report.py`; the capture path has no network calls. The report pipeline selects an inclusive event range, samples at most eight evenly spaced frames, reconstructs each one, applies every user-marked redaction, encodes the scrubbed image, then builds a Responses API request for `gpt-5.6`. The UI requires approval for each upload, renders the returned Markdown, and exposes one copy button.

## Privacy

- **Exclude regions** are blanked during capture and never enter the recording.
- **Redaction** applies user-marked rectangles to export copies and every report frame.
- **Cloud reports** stay off until the report dialog has a key and the per-request approval box is checked.
- Captured pixels and API keys are absent from logs. There is no telemetry, account system, or background sync.

## Built with Codex and GPT-5.6

I made the product calls: change-event storage, SQLite as the tamper-evident container, local-first capture, explicit cloud approval, spatial redaction before serialization, and an eight-frame ceiling for cost and latency. Codex accelerated the correctness work around those calls. It converted audit findings into regression tests, implemented the deterministic extraction and prompt path, wired the PySide6 report workspace, and ran the full sample and type-check passes after each commit. I reviewed the privacy boundary, sampling rule, prompt contract, error behavior, and release scope.

GPT-5.6 runs inside the shipped feature. It receives timestamped screenshots after Stutterbox applies the redaction pass, then returns one of two constrained Markdown shapes: bug reproduction steps or a session summary. The model prompt requires visible evidence, chronological claims, and a separate uncertainty section.

I also build coding agents. [Squadcode](https://github.com/mr-gl00m/squadcode) is my local, provider-agnostic coding-agent runtime, so I came in with strong opinions about normalized events, explicit permissions, inspectable transcripts, and local models as first-class tools. Codex gave me a useful comparison point against those choices. Stutterbox follows the same line: a narrow request, an explicit boundary, and an output the user can inspect before it leaves the app.

## Status

v0.2.0 release candidate. The local suite has 78 passing tests and `mypy --strict` is clean. The committed sample contains 507 change events at 1280x720; its chain verifies, all eight report frames prepare in 0.21 seconds, and the resulting PNG payload totals 39,107 bytes before Base64. Real capture has been exercised on Windows at 2560x1440. macOS and Linux use the same `mss` backend with less field time.

The final release gate is one approved live GPT-5.6 call against the bundled sample, followed by the public demo video. The optional Ed25519 signature remains deferred.

## What this isn't

Stutterbox is the recorder that refuses to be bossware. The upstream project will not accept features that turn personal capture into employee surveillance:

- No stealth capture or setting that suppresses recording state. Recording starts from a visible user action and exposes its state in the window and tray.
- No hidden autostart, service mode, or remote-start path.
- No automatic upload. A cloud report requires a user action, an API key, and approval for that request. Redaction runs before any selected frame is encoded for upload.
- No central collection, administrator console, telemetry, or background sync.
- No productivity scoring, activity ranking, attendance inference, or worker comparison.

These are structural omissions, not administrator settings. MIT permits forks to change that boundary. Upstream Stutterbox will stay deliberately incapable of those behaviors.

- No audio, smooth video, or streaming.
- No automatic content detection. Redaction is spatial and user-directed.
- No claim that a generated report can recover actions hidden between sampled frames.

## Support me

If you find this useful, consider supporting me and my research:

[![Ko-fi](https://img.shields.io/badge/Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/mr_gl00m)
[![GitHub Sponsors](https://img.shields.io/badge/GitHub_Sponsors-EA4AAA?style=for-the-badge&logo=github&logoColor=white)](https://github.com/sponsors/mr-gl00m)

**Crypto:**
- BTC: `bc1qnedeq3dr2dmlwgmw2mr5mtpxh45uhl395prr0d`
- ETH: `0x1bCbBa9854dA4Fc1Cb95997D5f42006055282e3c`
- SOL: `3Wm8wS93UpG2CrZsMWHSspJh7M5gQ6NXBbgLHDFXmAdQ`

## License

[MIT](LICENSE), Copyright (c) 2026 Cid.

## Contributing

Personal project, shared as-is. Issues and PRs are welcome with slow, opinionated review. More work lives under [mr-gl00m](https://github.com/mr-gl00m).
