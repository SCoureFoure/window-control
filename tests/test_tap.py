"""Tests for --tap command in orchestrator."""

from pathlib import Path

import pytest

from src.lens.model import Lens
from src.lens import store as lens_store
from src.actionmap.store import ActionMap
from src.actionmap import store as actionmap_store
from src.orchestrator import _cmd_tap


class FakeBackend:
    """Mock backend that records clicks."""
    def __init__(self):
        self.clicks = []

    def click(self, x, y, button="left"):
        self.clicks.append((x, y, button))

    def __getattr__(self, name):
        return lambda *a, **k: None


def test_tap_success_clicks_screen_absolute(tmp_path: Path):
    """Button "go" at [10, 20] on a 50x50 lens at (100, 200) should click (110, 220)."""
    # Setup: save lens at (100, 200, 50x50)
    lens = Lens(name="t", x=100, y=200, w=50, h=50)
    lens_store.save(lens, path=tmp_path / "lenses.json")

    # Setup: save action map with "go" button at [10, 20]
    amap = ActionMap(lens="t", buttons={"go": {"point": [10, 20]}})
    actionmap_store.save(amap, maps_dir=tmp_path)

    # Execute
    backend = FakeBackend()
    result = _cmd_tap("go", "t", lenses_path=tmp_path / "lenses.json", maps_dir=tmp_path, backend=backend)

    # Verify
    assert result == 0
    assert backend.clicks == [(110, 220, "left")]


def test_tap_unknown_button_returns_1(tmp_path: Path):
    """Tapping an unknown button should return 1 and not click."""
    # Setup: save lens and action map
    lens = Lens(name="t", x=100, y=200, w=50, h=50)
    lens_store.save(lens, path=tmp_path / "lenses.json")

    amap = ActionMap(lens="t", buttons={"known": {"point": [10, 20]}})
    actionmap_store.save(amap, maps_dir=tmp_path)

    # Execute
    backend = FakeBackend()
    result = _cmd_tap("unknown", "t", lenses_path=tmp_path / "lenses.json", maps_dir=tmp_path, backend=backend)

    # Verify
    assert result == 1
    assert backend.clicks == []


def test_tap_missing_map_returns_1(tmp_path: Path):
    """Tapping without an action map should return 1."""
    # Setup: save lens but no action map
    lens = Lens(name="t", x=100, y=200, w=50, h=50)
    lens_store.save(lens, path=tmp_path / "lenses.json")

    # Execute
    backend = FakeBackend()
    result = _cmd_tap("go", "t", lenses_path=tmp_path / "lenses.json", maps_dir=tmp_path, backend=backend)

    # Verify
    assert result == 1
    assert backend.clicks == []


def test_tap_missing_lens_returns_1(tmp_path: Path):
    """Tapping with a missing lens should return 1."""
    # Execute without setting up any lens
    backend = FakeBackend()
    result = _cmd_tap("go", "missing", lenses_path=tmp_path / "lenses.json", maps_dir=tmp_path, backend=backend)

    # Verify
    assert result == 1
    assert backend.clicks == []


def test_tap_out_of_bounds_returns_1_no_click(tmp_path: Path):
    """Tapping a button outside the lens should return 1 and not click."""
    # Setup: save lens at (100, 200, 50x50) and button at [999, 999] (out of bounds)
    lens = Lens(name="t", x=100, y=200, w=50, h=50)
    lens_store.save(lens, path=tmp_path / "lenses.json")

    amap = ActionMap(lens="t", buttons={"out": {"point": [999, 999]}})
    actionmap_store.save(amap, maps_dir=tmp_path)

    # Execute
    backend = FakeBackend()
    result = _cmd_tap("out", "t", lenses_path=tmp_path / "lenses.json", maps_dir=tmp_path, backend=backend)

    # Verify
    assert result == 1
    assert backend.clicks == []
