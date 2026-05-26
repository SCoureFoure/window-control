"""Capture zone — grab the lens region as a PIL image.

Returns a PIL Image so callers can optionally post-process (e.g. draw a
coordinate grid) before encoding. PNG encoding is a separate helper.
"""

from __future__ import annotations

import base64
import io

import mss
from PIL import Image

from src.lens.model import Lens

MIN_DIMENSION = 10


def capture(lens: Lens) -> Image.Image:
    """Screenshot the lens region. Returns a fresh PIL RGB image."""
    if lens.w < MIN_DIMENSION or lens.h < MIN_DIMENSION:
        raise ValueError(
            f"Lens {lens.name!r} is too small to capture: {lens.w}x{lens.h}px."
        )
    monitor = {"left": lens.x, "top": lens.y, "width": lens.w, "height": lens.h}
    with mss.mss() as sct:
        raw = sct.grab(monitor)
    return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


def encode_png_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")
