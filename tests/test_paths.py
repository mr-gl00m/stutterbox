from __future__ import annotations

from pathlib import Path

import pytest

from core.errors import ContainerError
from core.paths import is_within, validate_within_root


def test_path_inside_root_is_allowed(tmp_path: Path) -> None:
    root = tmp_path / "recordings"
    root.mkdir()
    target = root / "rec.stut"
    assert is_within(target, root)
    assert validate_within_root(target, root) == target.resolve()


def test_traversal_escapes_root(tmp_path: Path) -> None:
    root = tmp_path / "recordings"
    root.mkdir()
    escape = root / ".." / "secret.stut"
    assert not is_within(escape, root)
    with pytest.raises(ContainerError):
        validate_within_root(escape, root)


def test_absolute_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "recordings"
    root.mkdir()
    other = tmp_path / "elsewhere" / "rec.stut"
    with pytest.raises(ContainerError):
        validate_within_root(other, root)
