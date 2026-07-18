from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from core.model import Frame, Region


def _changed_tile_grid(
    prev: Frame, curr: Frame, *, threshold: int, tile: int
) -> NDArray[np.bool_]:
    """Return a boolean grid marking which tiles changed beyond ``threshold``.

    Change is measured as the maximum per-channel absolute difference at any
    pixel inside the tile — a single bright pixel flip marks the tile dirty,
    which is the conservative choice for a forensic recorder.
    """
    height, width = curr.shape[:2]
    # Max abs channel delta per pixel, as a small signed type to avoid overflow.
    delta = np.abs(curr.astype(np.int16) - prev.astype(np.int16)).max(axis=2)
    mask = delta > threshold

    n_ty = (height + tile - 1) // tile
    n_tx = (width + tile - 1) // tile
    pad_h = n_ty * tile - height
    pad_w = n_tx * tile - width
    if pad_h or pad_w:
        mask = np.pad(mask, ((0, pad_h), (0, pad_w)), constant_values=False)

    # (n_ty, tile, n_tx, tile) -> any-changed per tile.
    tiled = mask.reshape(n_ty, tile, n_tx, tile)
    return np.asarray(tiled.any(axis=(1, 3)))


def _label_components(grid: NDArray[np.bool_]) -> list[list[tuple[int, int]]]:
    """8-connected component labelling on a small boolean tile grid (no scipy).

    Diagonally touching changed tiles join one component, so a moving cursor
    and a popup notification stay as two separate boxes instead of merging
    into one screen-spanning rectangle.
    """
    n_ty, n_tx = grid.shape
    visited = np.zeros_like(grid, dtype=bool)
    components: list[list[tuple[int, int]]] = []
    for sy in range(n_ty):
        for sx in range(n_tx):
            if not grid[sy, sx] or visited[sy, sx]:
                continue
            stack: list[tuple[int, int]] = [(sy, sx)]
            visited[sy, sx] = True
            cells: list[tuple[int, int]] = []
            while stack:
                cy, cx = stack.pop()
                cells.append((cy, cx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = cy + dy, cx + dx
                        if (
                            0 <= ny < n_ty
                            and 0 <= nx < n_tx
                            and grid[ny, nx]
                            and not visited[ny, nx]
                        ):
                            visited[ny, nx] = True
                            stack.append((ny, nx))
            components.append(cells)
    return components


def changed_regions(
    prev: Frame, curr: Frame, *, threshold: int, tile: int
) -> list[Region]:
    """Compute bounded changed-region bounding boxes between two frames.

    Returns one ``Region`` per connected cluster of changed tiles, each
    clamped to the frame bounds. An empty list means nothing changed.
    """
    if prev.shape != curr.shape:
        raise ValueError(
            f"frame shape changed mid-capture: {prev.shape!r} -> {curr.shape!r}"
        )
    if tile <= 0:
        raise ValueError("tile size must be positive")

    height, width = curr.shape[:2]
    grid = _changed_tile_grid(prev, curr, threshold=threshold, tile=tile)
    if not grid.any():
        return []

    regions: list[Region] = []
    for cells in _label_components(grid):
        tys = [c[0] for c in cells]
        txs = [c[1] for c in cells]
        x0 = min(txs) * tile
        y0 = min(tys) * tile
        x1 = min((max(txs) + 1) * tile, width)
        y1 = min((max(tys) + 1) * tile, height)
        regions.append(Region(x0, y0, x1 - x0, y1 - y0))
    return regions
