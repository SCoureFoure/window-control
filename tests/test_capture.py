"""Tests for src/zones/capture.py — mss is mocked."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.lens.model import Lens
from src.zones.capture import capture, encode_png_b64


def _fake_grab(w: int, h: int):
    rgba = bytes([200, 100, 50, 255] * (w * h))
    return SimpleNamespace(size=(w, h), bgra=rgba)


def test_capture_grabs_lens_rect(monkeypatch):
    captured_monitor = {}

    class FakeMSS:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def grab(self, monitor):
            captured_monitor.update(monitor)
            return _fake_grab(monitor["width"], monitor["height"])

    monkeypatch.setattr("src.zones.capture.mss.mss", lambda: FakeMSS())
    lens = Lens(name="t", x=100, y=200, w=300, h=400)
    img = capture(lens)
    assert captured_monitor == {"left": 100, "top": 200, "width": 300, "height": 400}
    assert isinstance(img, Image.Image)
    assert img.size == (300, 400)


def test_capture_rejects_tiny_lens():
    lens = Lens(name="t", x=0, y=0, w=5, h=5)
    with pytest.raises(ValueError, match="too small"):
        capture(lens)


def test_encode_png_b64_produces_base64_string():
    img = Image.new("RGB", (10, 10), (255, 0, 0))
    b64 = encode_png_b64(img)
    assert isinstance(b64, str)
    assert len(b64) > 0
    import base64
    raw = base64.standard_b64decode(b64)
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
