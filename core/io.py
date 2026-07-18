from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write text to ``path`` atomically via tempfile + os.replace.

    A crash mid-write leaves the original file untouched instead of truncated.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path_str = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as fh:
            fh.write(content)
        os.replace(tmp_path, path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, data: Any, *, indent: int = 2) -> None:
    atomic_write_text(path, json.dumps(data, indent=indent, ensure_ascii=False) + "\n")


def atomic_publish_file(temp_path: Path, final_path: Path, *, overwrite: bool = False) -> None:
    """Publish a complete temp file atomically.

    The default path uses a hard link so an existing destination can never be
    replaced. Callers must opt in before replacement is allowed.
    """
    temp_path = Path(temp_path)
    final_path = Path(final_path)
    if overwrite:
        os.replace(temp_path, final_path)
        return

    os.link(temp_path, final_path)
    try:
        temp_path.unlink()
    except OSError:
        logger.warning(
            "Published %s but could not remove temporary file %s",
            final_path,
            temp_path,
            exc_info=True,
        )


def read_text(path: Path, encoding: str = "utf-8") -> str:
    return Path(path).read_text(encoding=encoding)


def read_json(path: Path) -> Any:
    return json.loads(read_text(path))
