from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

import numpy as np

from core.codec import MAX_REGION_PIXELS, decode_region
from core.config import MIGRATIONS_DIR
from core.errors import ContainerError, CorruptRecordingError
from core.hashchain import GENESIS_PREV_HASH, frame_digest
from core.model import ChangeEvent, Frame, FrameKind, RecordingMeta, Region

SCHEMA_VERSION: int = 1
SQLITE_MAGIC: bytes = b"SQLite format 3\x00"

# Input-normalization caps for opened (untrusted) recordings.
MAX_BLOB_BYTES: int = 64 * 1024 * 1024
MAX_DIMENSION: int = 32_768
MAX_FRAME_COUNT: int = 100_000
MAX_DURATION_MS: int = 31 * 24 * 60 * 60 * 1000
MAX_META_ROWS: int = 32

_REQUIRED_TABLES: frozenset[str] = frozenset({"meta", "frames"})
_FRAMES_COLUMNS: frozenset[str] = frozenset(
    {"id", "ts_ms", "kind", "x", "y", "w", "h", "blob", "frame_sha256", "prev_hash"}
)


def _frame_int(value: object, ordinal: int, name: str) -> int:
    if type(value) is not int:
        raise CorruptRecordingError(f"frame {ordinal} field {name} has an invalid type")
    return value


def _frame_text(value: object, ordinal: int, name: str) -> str:
    if not isinstance(value, str):
        raise CorruptRecordingError(f"frame {ordinal} field {name} has an invalid type")
    return value


@dataclass(frozen=True)
class FrameIndexRow:
    id: int
    ts_ms: int
    kind: FrameKind
    x: int
    y: int
    w: int
    h: int
    blob_len: int
    frame_sha256: str
    prev_hash: str

    @property
    def region(self) -> Region:
        return Region(self.x, self.y, self.w, self.h)


@dataclass(frozen=True)
class WriterStats:
    path: Path
    frame_count: int
    blob_bytes: int


def _discover_migrations() -> list[tuple[int, Path]]:
    found: list[tuple[int, Path]] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        prefix = path.name.split("_", 1)[0]
        try:
            number = int(prefix)
        except ValueError as exc:
            raise ContainerError(f"migration {path.name} lacks a numeric prefix") from exc
        found.append((number, path))
    found.sort(key=lambda item: item[0])
    return found


def _apply_migrations(conn: sqlite3.Connection) -> None:
    current = cast(int, conn.execute("PRAGMA user_version").fetchone()[0])
    for number, path in _discover_migrations():
        if number <= current:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        # ``number`` is a validated int, never user input — safe to inline.
        conn.execute(f"PRAGMA user_version = {number}")
        current = number


class RecordingWriter:
    """Writes a recording to a temp container with WAL crash-safety.

    On ``finalize`` the WAL is folded back so the artifact is a single file,
    ready for atomic publication to its final ``.stut`` path.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        try:
            # Autocommit mode: PRAGMA journal_mode must run outside a transaction.
            self._conn = sqlite3.connect(str(self._path), isolation_level=None)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            _apply_migrations(self._conn)
        except sqlite3.Error as exc:
            raise ContainerError(f"could not open writer at {self._path}: {exc}") from exc
        self._last_hash = GENESIS_PREV_HASH
        self._frame_count = 0
        self._blob_bytes = 0

    def write_meta(self, meta: RecordingMeta) -> None:
        rows: list[tuple[str, str]] = [
            ("schema_version", str(meta.schema_version)),
            ("app_version", meta.app_version),
            ("created_ms", str(meta.created_ms)),
            ("width", str(meta.width)),
            ("height", str(meta.height)),
            ("monitor", str(meta.monitor)),
            ("interval_ms", str(meta.interval_ms)),
            ("diff_threshold", str(meta.diff_threshold)),
            ("tile_size", str(meta.tile_size)),
            ("capture_format", meta.capture_format),
        ]
        try:
            self._conn.executemany(
                "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", rows
            )
        except sqlite3.Error as exc:
            raise ContainerError(f"failed to write meta: {exc}") from exc

    def append_frame(
        self, ts_ms: int, kind: FrameKind, region: Region, blob: bytes
    ) -> str:
        digest = frame_digest(self._last_hash, ts_ms, kind, region, blob)
        try:
            self._conn.execute(
                "INSERT INTO frames"
                "(ts_ms, kind, x, y, w, h, blob, frame_sha256, prev_hash) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ts_ms,
                    kind,
                    region.x,
                    region.y,
                    region.w,
                    region.h,
                    sqlite3.Binary(blob),
                    digest,
                    self._last_hash,
                ),
            )
        except sqlite3.Error as exc:
            raise ContainerError(f"failed to append frame: {exc}") from exc
        self._last_hash = digest
        self._frame_count += 1
        self._blob_bytes += len(blob)
        return digest

    def finalize(self) -> WriterStats:
        try:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._conn.execute("PRAGMA journal_mode=DELETE")
            self._conn.close()
        except sqlite3.Error as exc:
            raise ContainerError(f"failed to finalize recording: {exc}") from exc
        return WriterStats(self._path, self._frame_count, self._blob_bytes)

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass


class RecordingReader:
    """Opens a recording read-only, validating it as untrusted input."""

    def __init__(self, path: Path, *, verify: bool = True) -> None:
        self._path = Path(path)
        self._check_magic()
        try:
            uri = f"{self._path.resolve().as_uri()}?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True, isolation_level=None)
            self._conn.execute("PRAGMA query_only=ON")
            self._conn.execute("BEGIN")
        except sqlite3.Error as exc:
            raise CorruptRecordingError(f"recording will not open: {exc}") from exc

        self._validate_schema()
        self._meta = self._load_meta()
        self._index = self._load_index()
        self._events = self._build_events()
        if verify:
            self.verify_chain()

    # -- construction helpers ------------------------------------------------

    def _check_magic(self) -> None:
        try:
            with self._path.open("rb") as handle:
                header = handle.read(len(SQLITE_MAGIC))
        except OSError as exc:
            raise CorruptRecordingError(f"recording is unreadable: {exc}") from exc
        if header != SQLITE_MAGIC:
            raise CorruptRecordingError("not a SQLite recording container")

    def _validate_schema(self) -> None:
        try:
            version = cast(int, self._conn.execute("PRAGMA user_version").fetchone()[0])
            table_rows = self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            column_rows = self._conn.execute("PRAGMA table_info(frames)").fetchall()
        except sqlite3.Error as exc:
            raise CorruptRecordingError(f"schema is unreadable: {exc}") from exc

        if version != SCHEMA_VERSION:
            raise CorruptRecordingError(
                f"unsupported schema version {version}, expected {SCHEMA_VERSION}"
            )
        tables = {cast(str, row[0]) for row in table_rows}
        if not _REQUIRED_TABLES.issubset(tables):
            missing = ", ".join(sorted(_REQUIRED_TABLES - tables))
            raise CorruptRecordingError(f"recording missing tables: {missing}")
        columns = {cast(str, row[1]) for row in column_rows}
        if columns != _FRAMES_COLUMNS:
            raise CorruptRecordingError("frames table has an unexpected column set")

    def _load_meta(self) -> RecordingMeta:
        try:
            rows = self._conn.execute(
                "SELECT key, value FROM meta LIMIT ?", (MAX_META_ROWS + 1,)
            ).fetchall()
        except sqlite3.Error as exc:
            raise CorruptRecordingError(f"meta is unreadable: {exc}") from exc
        if len(rows) > MAX_META_ROWS:
            raise CorruptRecordingError("recording has too many metadata rows")

        raw: dict[str, str] = {}
        for key, value in rows:
            if not isinstance(key, str) or not isinstance(value, str):
                raise CorruptRecordingError("recording metadata has an invalid value type")
            if key in raw:
                raise CorruptRecordingError(f"meta key {key!r} is duplicated")
            raw[key] = value

        def _int(key: str) -> int:
            try:
                return int(raw[key])
            except (KeyError, ValueError) as exc:
                raise CorruptRecordingError(f"meta key {key!r} is missing or invalid") from exc

        def _text(key: str) -> str:
            try:
                return raw[key]
            except KeyError as exc:
                raise CorruptRecordingError(f"meta key {key!r} is missing") from exc

        meta = RecordingMeta(
            schema_version=_int("schema_version"),
            app_version=_text("app_version"),
            created_ms=_int("created_ms"),
            width=_int("width"),
            height=_int("height"),
            monitor=_int("monitor"),
            interval_ms=_int("interval_ms"),
            diff_threshold=_int("diff_threshold"),
            tile_size=_int("tile_size"),
            capture_format=_text("capture_format"),
        )
        if meta.schema_version != SCHEMA_VERSION:
            raise CorruptRecordingError("metadata schema version disagrees with the container")
        if not meta.app_version or len(meta.app_version) > 128:
            raise CorruptRecordingError("recording has an invalid app version")
        if meta.created_ms < 0:
            raise CorruptRecordingError("recording has a negative creation time")
        self._validate_wall_clock(meta.created_ms, "creation time")
        if meta.width <= 0 or meta.height <= 0:
            raise CorruptRecordingError("recording declares non-positive screen size")
        if meta.width > MAX_DIMENSION or meta.height > MAX_DIMENSION:
            raise CorruptRecordingError("recording declares an oversized screen")
        if meta.monitor < 0:
            raise CorruptRecordingError("recording declares a negative monitor")
        if not 0 <= meta.interval_ms <= 60_000:
            raise CorruptRecordingError("recording declares an invalid capture interval")
        if not 0 <= meta.diff_threshold <= 255:
            raise CorruptRecordingError("recording declares an invalid diff threshold")
        if not 1 <= meta.tile_size <= MAX_DIMENSION:
            raise CorruptRecordingError("recording declares an invalid tile size")
        if meta.capture_format != "png":
            raise CorruptRecordingError("recording declares an unsupported capture format")
        return meta

    @staticmethod
    def _validate_wall_clock(value_ms: int, label: str) -> None:
        try:
            datetime.fromtimestamp(value_ms / 1000.0)
        except (OSError, OverflowError, ValueError) as exc:
            raise CorruptRecordingError(f"recording {label} is out of range") from exc

    def _load_index(self) -> list[FrameIndexRow]:
        try:
            count_row = self._conn.execute("SELECT COUNT(*) FROM frames").fetchone()
            if count_row is None or type(count_row[0]) is not int:
                raise CorruptRecordingError("frame count has an invalid type")
            frame_count = count_row[0]
            if frame_count > MAX_FRAME_COUNT:
                raise CorruptRecordingError(
                    f"recording has {frame_count} frames, over the {MAX_FRAME_COUNT} cap"
                )
            rows = self._conn.execute(
                "SELECT id, ts_ms, kind, x, y, w, h, length(blob), typeof(blob), "
                "frame_sha256, prev_hash FROM frames ORDER BY id"
            ).fetchall()
        except sqlite3.Error as exc:
            raise CorruptRecordingError(f"frame index is unreadable: {exc}") from exc

        index: list[FrameIndexRow] = []
        for ordinal, row in enumerate(rows, start=1):
            kind = _frame_text(row[2], ordinal, "kind")
            if kind not in ("keyframe", "delta"):
                raise CorruptRecordingError(f"frame {row[0]} has unknown kind {kind!r}")
            blob_type = _frame_text(row[8], ordinal, "blob type")
            if blob_type != "blob":
                raise CorruptRecordingError(f"frame {ordinal} blob has an invalid type")
            entry = FrameIndexRow(
                id=_frame_int(row[0], ordinal, "id"),
                ts_ms=_frame_int(row[1], ordinal, "ts_ms"),
                kind=cast(FrameKind, kind),
                x=_frame_int(row[3], ordinal, "x"),
                y=_frame_int(row[4], ordinal, "y"),
                w=_frame_int(row[5], ordinal, "w"),
                h=_frame_int(row[6], ordinal, "h"),
                blob_len=_frame_int(row[7], ordinal, "blob length"),
                frame_sha256=_frame_text(row[9], ordinal, "frame_sha256"),
                prev_hash=_frame_text(row[10], ordinal, "prev_hash"),
            )
            if entry.id != ordinal:
                raise CorruptRecordingError(
                    f"frame id {entry.id} is out of sequence, expected {ordinal}"
                )
            if index and entry.ts_ms < index[-1].ts_ms:
                raise CorruptRecordingError(
                    f"frame {entry.id} breaks timestamp order"
                )
            self._validate_index_row(entry)
            index.append(entry)

        if index:
            self._validate_initial_keyframe(index[0])
            for row in index[1:]:
                if row.kind == "keyframe":
                    self._validate_full_screen_keyframe(row)
            self._validate_wall_clock(
                self._meta.created_ms + index[-1].ts_ms,
                "end time",
            )
        return index

    def _validate_index_row(self, row: FrameIndexRow) -> None:
        if row.ts_ms < 0:
            raise CorruptRecordingError(f"frame {row.id} has a negative timestamp")
        if row.ts_ms > MAX_DURATION_MS:
            raise CorruptRecordingError(
                f"frame {row.id} exceeds the recording duration cap"
            )
        if row.blob_len <= 0 or row.blob_len > MAX_BLOB_BYTES:
            raise CorruptRecordingError(
                f"frame {row.id} blob size {row.blob_len} is out of bounds"
            )
        if row.w <= 0 or row.h <= 0:
            raise CorruptRecordingError(f"frame {row.id} has a non-positive region")
        if row.w > MAX_DIMENSION or row.h > MAX_DIMENSION:
            raise CorruptRecordingError(f"frame {row.id} region exceeds the dimension cap")
        if row.x < 0 or row.y < 0:
            raise CorruptRecordingError(f"frame {row.id} has a negative coordinate")
        if row.w * row.h > MAX_REGION_PIXELS:
            raise CorruptRecordingError(f"frame {row.id} region exceeds the pixel cap")
        if row.x + row.w > self._meta.width or row.y + row.h > self._meta.height:
            raise CorruptRecordingError(f"frame {row.id} region falls outside the screen")
        for value in (row.frame_sha256, row.prev_hash):
            try:
                decoded = bytes.fromhex(value)
            except ValueError as exc:
                raise CorruptRecordingError(
                    f"frame {row.id} has a malformed hash field"
                ) from exc
            if len(decoded) != 32:
                raise CorruptRecordingError(f"frame {row.id} has a malformed hash field")

    def _is_full_screen(self, row: FrameIndexRow) -> bool:
        return (
            row.x == 0
            and row.y == 0
            and row.w == self._meta.width
            and row.h == self._meta.height
        )

    def _validate_initial_keyframe(self, row: FrameIndexRow) -> None:
        if row.kind != "keyframe":
            raise CorruptRecordingError("recording does not begin with a keyframe")
        if not self._is_full_screen(row):
            raise CorruptRecordingError(
                "recording does not begin with a full-screen keyframe"
            )

    def _validate_full_screen_keyframe(self, row: FrameIndexRow) -> None:
        # Every keyframe must cover the whole screen. reconstruct() starts from
        # the newest keyframe <= the target event, so a partial later keyframe
        # would zero every pixel it does not paint while the chain still
        # verifies. The recorder only ever writes the one initial keyframe.
        if not self._is_full_screen(row):
            raise CorruptRecordingError(
                f"frame {row.id} is a keyframe that does not cover the full screen"
            )

    def _build_events(self) -> list[ChangeEvent]:
        events: list[ChangeEvent] = []
        idx = 0
        n = len(self._index)
        while idx < n:
            ts = self._index[idx].ts_ms
            start = idx
            is_keyframe = False
            while idx < n and self._index[idx].ts_ms == ts:
                is_keyframe = is_keyframe or self._index[idx].kind == "keyframe"
                idx += 1
            group = self._index[start:idx]
            events.append(
                ChangeEvent(
                    index=len(events),
                    ts_ms=ts,
                    region_count=len(group),
                    last_frame_id=group[-1].id,
                    is_keyframe=is_keyframe,
                )
            )
        return events

    # -- public surface ------------------------------------------------------

    @property
    def meta(self) -> RecordingMeta:
        return self._meta

    @property
    def events(self) -> list[ChangeEvent]:
        return list(self._events)

    @property
    def frame_count(self) -> int:
        return len(self._index)

    @property
    def index(self) -> list[FrameIndexRow]:
        return list(self._index)

    def iter_frames(self) -> Iterator[tuple[FrameIndexRow, bytes]]:
        """Yield every frame row paired with its blob, in id order.

        Used by the export/redaction path, which rewrites each blob into a
        fresh container with its own valid hash chain.
        """
        try:
            blobs = self._conn.execute("SELECT id, blob FROM frames ORDER BY id")
            for row, (frame_id, blob) in zip(self._index, blobs, strict=True):
                if frame_id != row.id:
                    raise CorruptRecordingError("frame data changed during read")
                yield row, bytes(blob)
        except ValueError as exc:
            raise CorruptRecordingError("frame count changed during read") from exc
        except sqlite3.Error as exc:
            raise CorruptRecordingError(f"frame data is unreadable: {exc}") from exc

    def verify_chain(self) -> None:
        """Recompute the hash chain across every frame, blobs included.

        Raises ``CorruptRecordingError`` naming the first frame whose digest
        or prev-link does not match — the recording has been altered.
        """
        expected_prev = GENESIS_PREV_HASH
        for row, blob in self.iter_frames():
            if row.prev_hash != expected_prev:
                raise CorruptRecordingError(
                    f"hash chain breaks at frame {row.id}: prev-link mismatch"
                )
            digest = frame_digest(row.prev_hash, row.ts_ms, row.kind, row.region, blob)
            if digest != row.frame_sha256:
                raise CorruptRecordingError(
                    f"hash chain breaks at frame {row.id}: content was altered"
                )
            expected_prev = row.frame_sha256

    def reconstruct(self, event_index: int) -> Frame:
        """Rebuild the full screen as it stood at the given change event."""
        if not self._events:
            raise CorruptRecordingError("recording has no change events")
        if event_index < 0 or event_index >= len(self._events):
            raise IndexError(f"event index {event_index} out of range")

        target_id = self._events[event_index].last_frame_id
        keyframe_id = self._latest_keyframe_id(target_id)
        canvas: Frame = np.zeros((self._meta.height, self._meta.width, 3), dtype=np.uint8)

        try:
            rows = self._conn.execute(
                "SELECT x, y, w, h, blob FROM frames "
                "WHERE id >= ? AND id <= ? ORDER BY id",
                (keyframe_id, target_id),
            )
            for x, y, w, h, blob in rows:
                patch = decode_region(bytes(blob))
                if patch.shape[0] != h or patch.shape[1] != w:
                    raise CorruptRecordingError(
                        "frame blob dimensions disagree with the stored region"
                    )
                canvas[y : y + h, x : x + w] = patch
        except sqlite3.Error as exc:
            raise CorruptRecordingError(f"frame data is unreadable: {exc}") from exc
        return canvas

    def _latest_keyframe_id(self, target_id: int) -> int:
        keyframe_id = -1
        for row in self._index:
            if row.id > target_id:
                break
            if row.kind == "keyframe":
                keyframe_id = row.id
        if keyframe_id < 0:
            raise CorruptRecordingError("no keyframe precedes the requested event")
        return keyframe_id

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    def __enter__(self) -> "RecordingReader":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
