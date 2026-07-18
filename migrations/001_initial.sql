-- Stutterbox recording container, schema version 1.
-- Pragmas (WAL, foreign_keys) are applied in code per connection, not here.

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Every keyframe and delta region is one row. The (frame_sha256, prev_hash)
-- pair forms a hash chain across the whole recording: this table doubles as
-- the integrity guarantee and as SIGIL's tamper-evident audit log.
CREATE TABLE frames (
    id           INTEGER PRIMARY KEY,
    ts_ms        INTEGER NOT NULL,
    kind         TEXT    NOT NULL CHECK (kind IN ('keyframe', 'delta')),
    x            INTEGER NOT NULL CHECK (x >= 0),
    y            INTEGER NOT NULL CHECK (y >= 0),
    w            INTEGER NOT NULL CHECK (w >= 0),
    h            INTEGER NOT NULL CHECK (h >= 0),
    blob         BLOB    NOT NULL,
    frame_sha256 TEXT    NOT NULL,
    prev_hash    TEXT    NOT NULL
);

CREATE INDEX idx_frames_ts ON frames (ts_ms);
