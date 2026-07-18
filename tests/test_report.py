from __future__ import annotations

import base64
from pathlib import Path

import numpy as np
import pytest

from conftest import low_motion_frames, record_frames
from core.codec import decode_region
from core.container import RecordingReader
from core.errors import ReportError
from core.model import Region
from core.report import (
    REPORT_MODEL,
    _extract_report_text,
    generate_report,
    prepare_report,
    select_event_indices,
)

WIDTH, HEIGHT = 160, 120


def _reader(tmp_path: Path, count: int = 12) -> RecordingReader:
    frames = low_motion_frames(WIDTH, HEIGHT, count)
    path, _ = record_frames(tmp_path, frames, width=WIDTH, height=HEIGHT)
    return RecordingReader(path)


def test_event_selection_is_inclusive_evenly_spaced_and_capped(tmp_path: Path) -> None:
    with _reader(tmp_path, count=20) as reader:
        indices = select_event_indices(reader.events, 2, 17, limit=5)
    assert indices == [2, 5, 9, 13, 17]


def test_prepared_keyframes_keep_event_timestamps(tmp_path: Path) -> None:
    with _reader(tmp_path) as reader:
        prepared = prepare_report(
            reader,
            2,
            9,
            report_kind="session_summary",
            redactions=[],
            limit=4,
        )
        expected = [(index, reader.events[index].ts_ms) for index in (2, 4, 6, 9)]
    actual = [(item.event_index, item.ts_ms) for item in prepared.snapshots]
    assert actual == expected
    assert prepared.payload["model"] == REPORT_MODEL == "gpt-5.6"


def test_redaction_is_baked_before_image_enters_payload(tmp_path: Path) -> None:
    redaction = Region(0, 0, 48, 48)
    with _reader(tmp_path) as reader:
        prepared = prepare_report(
            reader,
            0,
            len(reader.events) - 1,
            report_kind="bug_repro",
            redactions=[redaction],
            limit=3,
        )

    request_input = prepared.payload["input"]
    assert isinstance(request_input, list)
    message = request_input[0]
    assert isinstance(message, dict)
    content = message["content"]
    assert isinstance(content, list)
    image_items = [item for item in content if item.get("type") == "input_image"]
    assert len(image_items) == 3
    for item in image_items:
        image_url = item["image_url"]
        assert isinstance(image_url, str)
        encoded = image_url.removeprefix("data:image/png;base64,")
        frame = decode_region(base64.b64decode(encoded))
        assert np.all(frame[0:48, 0:48] == 0)


def test_response_text_is_collected_from_message_blocks() -> None:
    payload: object = {
        "output": [
            {"type": "reasoning", "summary": []},
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "# Report"},
                    {"type": "output_text", "text": "Body"},
                ],
            },
        ]
    }
    assert _extract_report_text(payload) == "# Report\n\nBody"


def test_missing_api_key_fails_before_network(tmp_path: Path) -> None:
    with _reader(tmp_path) as reader:
        prepared = prepare_report(
            reader,
            0,
            0,
            report_kind="session_summary",
            redactions=[],
        )
    with pytest.raises(ReportError, match="API key"):
        generate_report("", prepared)
