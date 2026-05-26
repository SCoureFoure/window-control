"""Tests for the coord-grid overlay."""

import pytest
from PIL import Image

from src.lens.grid import draw_grid


def test_dimensions_preserved():
    img = Image.new("RGB", (200, 150), (50, 50, 50))
    out = draw_grid(img, spacing=50)
    assert out.size == (200, 150)
    assert out.mode == "RGB"


def test_grid_modifies_pixels():
    img = Image.new("RGB", (200, 150), (50, 50, 50))
    out = draw_grid(img, spacing=50)
    assert out.tobytes() != img.tobytes()


def test_invalid_spacing():
    img = Image.new("RGB", (10, 10), (0, 0, 0))
    with pytest.raises(ValueError):
        draw_grid(img, spacing=0)
