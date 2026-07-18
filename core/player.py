from __future__ import annotations

from pathlib import Path

from core.container import RecordingReader
from core.model import ChangeEvent, Frame, RecordingMeta


class Player:
    """Stateful playback over a recording: open, seek, step change-to-change.

    Navigation is by change event, not by seconds — ``next_change`` lands on
    the moment something on screen actually changed.
    """

    def __init__(self, path: Path, *, verify: bool = True) -> None:
        self._reader = RecordingReader(path, verify=verify)
        self._index = 0

    @property
    def reader(self) -> RecordingReader:
        return self._reader

    @property
    def meta(self) -> RecordingMeta:
        return self._reader.meta

    @property
    def events(self) -> list[ChangeEvent]:
        return self._reader.events

    @property
    def event_count(self) -> int:
        return len(self._reader.events)

    @property
    def current_index(self) -> int:
        return self._index

    @property
    def current_event(self) -> ChangeEvent:
        return self._reader.events[self._index]

    def seek(self, index: int) -> Frame:
        count = self.event_count
        if count == 0:
            raise IndexError("recording has no change events")
        self._index = max(0, min(index, count - 1))
        return self._reader.reconstruct(self._index)

    def frame(self) -> Frame:
        return self._reader.reconstruct(self._index)

    def next_change(self) -> Frame:
        return self.seek(self._index + 1)

    def prev_change(self) -> Frame:
        return self.seek(self._index - 1)

    def has_next(self) -> bool:
        return self._index < self.event_count - 1

    def has_prev(self) -> bool:
        return self._index > 0

    def close(self) -> None:
        self._reader.close()

    def __enter__(self) -> "Player":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
