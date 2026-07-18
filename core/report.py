from __future__ import annotations

import base64
import json
import socket
from collections.abc import Sequence
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Literal, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.codec import encode_region
from core.container import RecordingReader
from core.errors import ReportError
from core.model import ChangeEvent, Region
from core.redaction import redact_frame

OPENAI_RESPONSES_URL: str = "https://api.openai.com/v1/responses"
REPORT_MODEL: str = "gpt-5.6"
MAX_REPORT_FRAMES: int = 8
MAX_RESPONSE_BYTES: int = 4 * 1024 * 1024
REPORT_TIMEOUT_SECONDS: float = 90.0

ReportKind = Literal["bug_repro", "session_summary"]


@dataclass(frozen=True)
class ReportSnapshot:
    event_index: int
    ts_ms: int
    png_bytes: bytes


@dataclass(frozen=True)
class PreparedReport:
    payload: dict[str, object]
    snapshots: tuple[ReportSnapshot, ...]


def select_event_indices(
    events: Sequence[ChangeEvent],
    start_event: int,
    end_event: int,
    *,
    limit: int = MAX_REPORT_FRAMES,
) -> list[int]:
    """Select an inclusive, evenly spaced event range with stable endpoints."""
    if not events:
        raise ValueError("recording has no change events")
    if limit <= 0:
        raise ValueError("report frame limit must be positive")
    if start_event < 0 or end_event >= len(events) or start_event > end_event:
        raise ValueError("report event range is invalid")

    count = end_event - start_event + 1
    selected_count = min(count, limit)
    if selected_count == 1:
        return [start_event]
    span = count - 1
    return [
        start_event + (slot * span) // (selected_count - 1)
        for slot in range(selected_count)
    ]


def extract_report_snapshots(
    reader: RecordingReader,
    start_event: int,
    end_event: int,
    *,
    redactions: list[Region],
    limit: int = MAX_REPORT_FRAMES,
) -> tuple[ReportSnapshot, ...]:
    """Reconstruct, redact, then encode the selected change-event frames."""
    events = reader.events
    indices = select_event_indices(events, start_event, end_event, limit=limit)
    snapshots: list[ReportSnapshot] = []
    for event_index in indices:
        frame = reader.reconstruct(event_index)
        redacted = redact_frame(frame, redactions)
        snapshots.append(
            ReportSnapshot(
                event_index=event_index,
                ts_ms=events[event_index].ts_ms,
                png_bytes=encode_region(redacted),
            )
        )
    return tuple(snapshots)


def build_report_prompt(
    report_kind: ReportKind,
    events: Sequence[ChangeEvent],
    start_event: int,
    end_event: int,
    snapshots: Sequence[ReportSnapshot],
) -> str:
    """Build the deterministic text instruction paired with report images."""
    if report_kind == "bug_repro":
        requested_sections = (
            "# Bug reproduction report\n"
            "## Observed behavior\n"
            "## Reproduction steps\n"
            "## Expected and actual result\n"
            "## Evidence timeline\n"
            "## Uncertainties"
        )
    elif report_kind == "session_summary":
        requested_sections = (
            "# Session summary\n"
            "## Overview\n"
            "## Timeline\n"
            "## Changes and decisions\n"
            "## Open items\n"
            "## Uncertainties"
        )
    else:
        raise ValueError(f"unknown report kind: {report_kind}")

    first_ts = events[start_event].ts_ms
    last_ts = events[end_event].ts_ms
    return (
        "Analyze the timestamped screenshots from one Stutterbox recording. "
        "Return GitHub-flavored Markdown using the exact section order below. "
        "Follow visible evidence and chronology. Do not invent hidden actions, "
        "causes, user intent, or events between sampled frames. Put any uncertain "
        "claim in the Uncertainties section. Keep reproduction steps specific and "
        "actionable when the screenshots support them.\n\n"
        f"Selected event range: {start_event + 1} to {end_event + 1} of "
        f"{len(events)}.\n"
        f"Selected time range: {_format_ts(first_ts)} to {_format_ts(last_ts)}.\n"
        f"Attached sampled frames: {len(snapshots)}.\n\n"
        f"{requested_sections}"
    )


def prepare_report(
    reader: RecordingReader,
    start_event: int,
    end_event: int,
    *,
    report_kind: ReportKind,
    redactions: list[Region],
    limit: int = MAX_REPORT_FRAMES,
) -> PreparedReport:
    """Create a Responses API payload after the local redaction stage."""
    events = reader.events
    snapshots = extract_report_snapshots(
        reader,
        start_event,
        end_event,
        redactions=redactions,
        limit=limit,
    )
    prompt = build_report_prompt(
        report_kind, events, start_event, end_event, snapshots
    )

    content: list[dict[str, object]] = [{"type": "input_text", "text": prompt}]
    for snapshot in snapshots:
        encoded = base64.b64encode(snapshot.png_bytes).decode("ascii")
        content.append(
            {
                "type": "input_text",
                "text": (
                    f"Event {snapshot.event_index + 1} at "
                    f"{_format_ts(snapshot.ts_ms)}"
                ),
            }
        )
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{encoded}",
                "detail": "high",
            }
        )

    payload: dict[str, object] = {
        "model": REPORT_MODEL,
        "input": [{"role": "user", "content": content}],
        "reasoning": {"effort": "low"},
        "max_output_tokens": 2500,
    }
    return PreparedReport(payload=payload, snapshots=snapshots)


def generate_report(
    api_key: str,
    prepared: PreparedReport,
    *,
    timeout: float = REPORT_TIMEOUT_SECONDS,
) -> str:
    """Submit a prepared payload and return the generated Markdown."""
    key = api_key.strip()
    if not key:
        raise ReportError("Add an OpenAI API key before generating a report.")
    if len(key) > 512 or any(ord(char) < 32 for char in key):
        raise ReportError("The OpenAI API key has an invalid format.")

    body = json.dumps(prepared.payload, separators=(",", ":")).encode("utf-8")
    request = Request(
        OPENAI_RESPONSES_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = cast(bytes, response.read(MAX_RESPONSE_BYTES + 1))
    except HTTPError as exc:
        raise ReportError(_http_error_message(exc)) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise ReportError("OpenAI did not respond before the request timed out.") from exc
    except URLError as exc:
        raise ReportError("OpenAI is unreachable. Check the network and try again.") from exc
    except OSError as exc:
        raise ReportError("The report request could not be sent.") from exc

    if len(raw) > MAX_RESPONSE_BYTES:
        raise ReportError("OpenAI returned an unexpectedly large response.")
    try:
        response_payload: object = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, JSONDecodeError) as exc:
        raise ReportError("OpenAI returned an unreadable response.") from exc
    return _extract_report_text(response_payload)


def _extract_report_text(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ReportError("OpenAI returned an unexpected response shape.")
    output = payload.get("output")
    if not isinstance(output, list):
        raise ReportError("OpenAI returned no report text.")
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "output_text":
                continue
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    if not parts:
        raise ReportError("OpenAI returned no report text.")
    return "\n\n".join(parts)


def _http_error_message(exc: HTTPError) -> str:
    if exc.code == 401:
        return "OpenAI rejected the API key. Check the saved key and try again."
    if exc.code == 429:
        return "OpenAI rate-limited the request. Wait briefly and try again."
    if 500 <= exc.code <= 599:
        return "OpenAI is temporarily unavailable. Try again shortly."
    return f"OpenAI rejected the report request with HTTP {exc.code}."


def _format_ts(ts_ms: int) -> str:
    seconds, millis = divmod(ts_ms, 1000)
    minutes, secs = divmod(seconds, 60)
    hours, mins = divmod(minutes, 60)
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}.{millis:03d}"
    return f"{mins}:{secs:02d}.{millis:03d}"
