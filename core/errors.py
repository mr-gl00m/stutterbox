from __future__ import annotations


class StutterboxError(Exception):
    """Base class for every Stutterbox domain error."""


class CaptureError(StutterboxError):
    """A screen grab or the capture loop failed."""


class ReportError(StutterboxError):
    """A cloud report could not be prepared or generated."""


class ContainerError(StutterboxError):
    """A recording container could not be created, written, or queried."""


class CorruptRecordingError(ContainerError):
    """An opened recording failed validation or hash-chain verification.

    Carries a human-readable ``reason`` so the UI can surface why a file was
    rejected without leaking captured pixels or stack internals.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
