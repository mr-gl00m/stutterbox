from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage

from core.model import Frame


def frame_to_qimage(frame: Frame) -> QImage:
    """Convert a contiguous RGB uint8 frame to a detached QImage."""
    contiguous = np.ascontiguousarray(frame, dtype=np.uint8)
    height, width, _ = contiguous.shape
    image = QImage(
        contiguous.data,
        width,
        height,
        3 * width,
        QImage.Format.Format_RGB888,
    )
    # copy() detaches from the numpy buffer so the array can be freed.
    return image.copy()
