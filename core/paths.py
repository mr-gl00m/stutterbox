from __future__ import annotations

from pathlib import Path

from core.errors import ContainerError


def is_within(path: Path, root: Path) -> bool:
    """True if ``path`` resolves to a location inside ``root``."""
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
    except ValueError:
        return False
    return True


def validate_within_root(path: Path, root: Path) -> Path:
    """Return the resolved ``path`` if inside ``root``, else raise.

    Guards save/open against traversal — a recording path must stay under the
    recordings root, never escape it via ``..`` or an absolute redirect.
    """
    resolved = Path(path).resolve()
    if not is_within(resolved, root):
        raise ContainerError(f"path {resolved} escapes the recordings root {root}")
    return resolved
