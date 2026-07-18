# OpenAI Build Week submission handoff

Status: feature complete locally, external submission actions open.

Official deadline: Tuesday, July 21, 2026 at 5:00 PM PT.

Category: Work & Productivity

Repository: https://github.com/mr-gl00m/stutterbox

Codex Session ID candidate: `019f75bc-4574-70e2-8520-79fb5dcbcde7`

Before submission, run `/feedback` in the primary build thread and confirm that the returned Session ID matches this value. Paste the `/feedback` value into Devpost.

## Devpost description

Stutterbox turns low-motion screen recordings into small, tamper-evident work logs that scrub by change-event. Instead of storing every full frame, it keeps one keyframe plus lossless changed regions and timestamps inside a SQLite `.stut` container. That makes a coding, debugging, or support session quick to inspect without treating it like ordinary video.

For Build Week, Stutterbox adds an opt-in GPT-5.6 report path. A user opens a recording, chooses the full session or an event range, marks spatial redactions, and approves the request. Stutterbox reconstructs up to eight timestamped change-event frames, applies redaction locally before image encoding, sends the narrow payload to GPT-5.6, renders a bug reproduction report or session summary, and copies the Markdown in one click. The bundled 507-event sample lets a judge test the full path with an API key without recording a new session.

Stutterbox v0.1.0 shipped on June 2, 2026 with the local recorder, change-event player, export, and tamper-evident `.stut` container. The Build Week extension adds the complete GPT-5.6 report loop, its opt-in desktop workflow, deterministic tests, release hardening, and the Windows judge package. The public `v0.1.0...main` comparison preserves that boundary.

The product position is deliberate: Stutterbox refuses stealth capture, hidden autostart, automatic upload, central collection, and productivity scoring. A report starts with a visible user action, requires approval for that request, and receives only frames redacted on the local machine.

## Required artifact checklist

- [x] Public repository contains the reviewed source snapshot and MIT license.
- [x] Third-party runtime components and license terms are documented and bundled with the Windows build.
- [ ] Public YouTube demo is below three minutes and linked in Devpost.
- [ ] `/feedback` Session ID confirmed against the candidate above.
- [x] README explains setup, sample data, Codex acceleration, product decisions, GPT-5.6 use, and Squadcode context.
- [ ] Public v0.2.0 Windows test build is linked in Devpost testing instructions.
- [ ] Public build and repository will remain free and available through the end of judging.

## Evidence after July 13

Public evidence: the repository upload, release publication, and asset timestamps all fall inside the July 13 to 21 window on GitHub's server-side clock.

Local history reference (not visible on the public snapshot):

- `e2a6f85` through `9831a42`: same-day recording safety and untrusted-input hardening.
- `0a2f3e4`: redacted GPT-5.6 report pipeline plus deterministic regression tests.
- `e1da13e`: opt-in PySide6 report workspace and local API key setting.
- This documentation and release commit follows as a separate history entry.

## Judge-facing assets

- Devpost thumbnail: `.photos/stutterbox.png`. This is the project-owned application icon.
- Gallery still 1: the sample open in the main window with the 507-event count, heat map, and visible recording state.
- Gallery still 2: the report workspace showing a selected range, a visible redaction, upload approval, and rendered Markdown. Keep the API key field masked.
- Test build: `Stutterbox-v0.2.0-win64.zip`. A judge should extract the full folder and run `Stutterbox.exe`; the executable is not standalone outside that folder.
- Test data: `samples/sample_coding_session.stut`, also bundled inside the Windows ZIP.

Use the app icon as the thumbnail. Favor interface evidence over a decorative banner because judges may evaluate from the submission page without running the build.

## Judging case

- **Technological implementation:** Codex-assisted development shows in the regression tests, strict typing, hostile-input boundaries, and the complete GPT-5.6 feature path in the public source.
- **Design:** one desktop workflow covers selection, local redaction, explicit approval, generation, rendered output, copy, and visible error states.
- **Potential impact:** bug reports and work-session summaries become reproducible artifacts without uploading a continuous screen recording.
- **Quality of the idea:** change-event storage and an upstream refusal to support bossware give the recorder a specific technical and product identity.

These points should appear through the description, stills, and narration. Do not rely on judges running the app to discover them.

## Live acceptance run

1. Start with `uv run python main.py`.
2. Open `samples/sample_coding_session.stut`.
3. Click **Redact** and mark one visible region.
4. Click **Generate report**.
5. Choose **Bug reproduction report**, events 1 to 507.
6. Enter the API key and approve the upload for that request.
7. Generate, inspect the rendered Markdown, and click **Copy report**.
8. Confirm the report is on the clipboard and the UI remains responsive.

Record the generated report only after checking it for captured secrets. Never show the API key in the demo.

## Demo video shot list

Target length: 2 minutes 30 seconds. The official limit is below three minutes.

- 0:00 to 0:15: state the problem and show the 272 KiB sample beside the raw-frame comparison.
- 0:15 to 0:40: open the sample, scrub by change, and show the verified event count.
- 0:40 to 1:00: mark a redaction region and explain that it is applied before encoding.
- 1:00 to 1:35: open Generate report, select the range, show the masked key field, approve, and run GPT-5.6.
- 1:35 to 1:55: show rendered reproduction steps and copy the Markdown.
- 1:55 to 2:20: cover the Codex build story, the decisions kept human, and the Squadcode perspective.
- 2:20 to 2:30: show the local README, MIT license, sample path, and passing `uv run python -m pytest` output.

Audio must explain both Codex and GPT-5.6 use. Use original music or no music.

Keep unrelated brand marks, notifications, account names, secrets, and browser chrome out of the recording. Use the project-owned icon and application UI. Review the final upload at full resolution before linking it.

## External finish list

- [ ] Run the live acceptance pass once with an approved API key.
- [ ] Commit a scrubbed generated sample report if it adds value.
- [x] Build the v0.2.0 Windows package and run its smoke check.
- [x] Upload the reviewed source snapshot to public `main`.
- [ ] Confirm the `/feedback` Session ID from the primary build thread.
- [ ] Capture the two judge-facing gallery stills and upload `.photos/stutterbox.png` as the thumbnail.
- [ ] Download the published Windows ZIP into a clean folder and repeat the sample workflow.
- [ ] Recreate the `v0.2.0` tag and release through the web UI.
- [ ] Publish the GitHub Release with notes, Windows ZIP, source archive, and SHA256 checksums.
- [ ] Add the public YouTube URL here and to the README if useful.
- [ ] Swap Stutterbox into GitHub profile pin slot 6.
- [ ] Submit the Devpost form before the deadline.

Official challenge page: https://openai.devpost.com/

Official rules: https://openai.devpost.com/rules
