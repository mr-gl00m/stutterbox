# Stutterbox real-display QA gate

Human-run. An autonomous run cannot close this: it needs a live display with
real motion, and the committed sample is synthetic. Budget fifteen minutes.
This walks the full app, not just the capture harness. For the fast
harness-only path see `.docs/real_display_verification.md`.

Fill the Result column PASS or FAIL as you go. Any FAIL leaves the gate open.

## 0. Environment

- Windows 11, real monitor attached and awake (not a locked or off screen).
- Run from the project venv: `uv run python main.py`.
- Defaults in `~/.proj_stutterbox/settings.json` (written on first run):
  `monitor=1`, `interval_ms=250`, `diff_threshold=12`, `tile_size=48`.
  If your target changes will be on a second display, set `monitor` to that
  index before starting, or move the changes to monitor 1.
- Have a throwaway window ready to open mid-capture (Notepad works).
- Do not put anything genuinely secret on screen. This produces a real
  recording file on disk.

## 1. Display setup checks

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 1.1 | Launch `uv run python main.py` | Dark window titled "Stutterbox", amber accent, no traceback in `logs/stutterbox.log` | |
| 1.2 | Look at the control row | Record enabled; Stop, Export, Redact, Clear redactions, Copy frame, Copy share snippet disabled (no player yet) | |

## 2. Capture

Capture duration: at least 2 minutes of real, motion-bearing use. Idle screens
produce zero events and count as a FAIL.

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 2.1 | Click Record | The amber `● REC` indicator appears; status reads "Recording" with a "0 events" count; Record disabled, Stop enabled | |
| 2.2 | At about 0:30, open Notepad on the captured monitor | Status event count climbs above zero within a tick or two | |
| 2.3 | At about 1:00, type a findable line, e.g. `STUTTERBOX REAL VERIFY`, and note the wall-clock moment | Event count keeps climbing as you type | |
| 2.4 | At about 1:40, close Notepad | Event count ticks up on the close | |
| 2.5 | Work normally to about 2:00, then click Stop | Status shows "Finalizing…", then a "Saved rec_YYYYMMDD_HHMMSS.stut" line with the event, frame, and KiB counts; the recording auto-opens and the first frame renders | |

Expected output file path (default recordings folder):

```
C:\Users\<you>\.proj_stutterbox\recordings\rec_YYYYMMDD_HHMMSS.stut
```

The timestamp matches when you hit Record. A crash or force-quit before Stop
must leave NO `.stut` at that path (only the temp `.rec_*.stut.tmp` may appear
mid-run, and it is removed on a clean stop).

## 3. Open and scrub (the ship criterion)

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 3.1 | The recording auto-opened after Stop. Confirm the status line | Names the file, then "N change events, WxH, chain verified" (N > 0) | |
| 3.2 | Close and reopen it: click Open, pick the file from the recordings folder | It opens again; this manual open runs full hash-chain verification (the auto-open after Stop skips re-verify because the file was just written and trusted) | |
| 3.3 | Read the event info line under the frame | `event k/N · m:ss.mmm · R region(s)` | |
| 3.4 | Click `Next change ›` repeatedly, or click the timeline | The frame updates and lands on the moment of a change, not a fixed time step | |
| 3.5 | Scrub to the event where Notepad appeared | The frame shows Notepad on screen where it was not before; the event timestamp roughly matches step 2.2 | |
| 3.6 | Scrub to the event where your line was typed | `STUTTERBOX REAL VERIFY` is legible in the frame | |
| 3.7 | Scrub to the event after 2.4 | Notepad is gone | |
| 3.8 | `‹ Previous change` from event 0, and `Next change ›` at the last event | The buttons no-op or disable at each end; no crash, no wrap | |

## 4. Export with redaction

This proves the share-time privacy control. Coverage is spatial only: it zeroes
the pixels under a box, it does not detect content.

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 4.1 | Scrub to the frame where your typed line is visible | Line is on screen | |
| 4.2 | Click Redact (it stays pressed), then drag a box over the typed line on the frame | Status: "Drag on the frame to mark redaction regions"; a redaction rectangle appears over the text | |
| 4.3 | Click Export | A confirm dialog appears warning the recording can hold secrets and stating "N redaction region(s) will be baked into the exported copy"; default button is Cancel | |
| 4.4 | Click OK, choose a destination filename in the save dialog | Non-`.stut` names get `.stut` appended; status confirms "Exported NAME" with the frame count and "K redacted", K >= 1 | |
| 4.5 | Open the exported copy with Open | It verifies (fresh valid chain) and opens | |
| 4.6 | Scrub to the same typed-line event in the export | The redacted box is solid black; the text is gone and not recoverable | |
| 4.7 | Reopen the ORIGINAL recording, same event | The text is still there; the original was not modified | |

Overwrite warning: choosing an existing export path opens a second confirmation
dialog. Cancel keeps the existing recording unchanged.

## 5. Optional: exclude-at-capture

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 5.1 | Click Exclude regions, box an area of the screen, save | "N exclude region(s) saved"; the box is stored in settings | |
| 5.2 | Record a short session with visible change happening inside that boxed area, then Stop and open | Reconstructed frames show that area as constant black at every event; changes outside it still record | |

## Pass bar

All of the following, or the gate stays open. Do not soften any line.

- Capture ran on a real display for 2+ minutes with real motion.
- Recording saved to the expected path; N change events with N > 0.
- Manual Open verifies the chain and opens without error.
- `Next change` lands on your three deliberate changes (Notepad open, typed
  line, Notepad close) at roughly the right timestamps. A black or static
  frame is a FAIL.
- End buttons no-op or disable at both ends; no crash, no wrap.
- Redacted export: the redacted box is black, the text is gone, the export
  verifies, and the original is untouched.

A zero-event recording is a FAIL, not a pass.

## Evidence

- Date run:
- Machine / display resolution:
- Recording path and size:
- Change-event count:
- Notes (which steps passed, anything odd):

When every row above reads PASS, flip the human item in `checklist.txt`
("real multi-minute capture opens and jumps to a known change") to `[x]` and
paste this Evidence block plus the harness output into it.
