"""Tests for action map storage and resolution."""

from pathlib import Path

import pytest

from src.actionmap import store
from src.actionmap.store import ActionMap


def test_save_load_roundtrip(tmp_path: Path):
    """Test that an action map can be saved and loaded back identically."""
    amap = ActionMap(lens="uma", buttons={"settings": {"point": [1043, 256]}})
    store.save(amap, maps_dir=tmp_path)
    loaded = store.load("uma", maps_dir=tmp_path)
    assert loaded.lens == amap.lens
    assert loaded.buttons == amap.buttons


def test_load_missing_raises(tmp_path: Path):
    """Test that loading a missing action map raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        store.load("nope", maps_dir=tmp_path)


def test_resolve_point():
    """Test that a point button resolves to its coordinates."""
    amap = ActionMap(lens="test", buttons={"btn": {"point": [1043, 256]}})
    assert store.resolve(amap, "btn") == (1043, 256)


def test_resolve_rect_center():
    """Test that a rect button resolves to its center."""
    # {"rect": [0, 0, 80, 80]} -> (40, 40)
    amap = ActionMap(lens="test", buttons={"btn1": {"rect": [0, 0, 80, 80]}})
    assert store.resolve(amap, "btn1") == (40, 40)

    # {"rect": [10, 20, 5, 5]} -> (12, 22)
    amap = ActionMap(lens="test", buttons={"btn2": {"rect": [10, 20, 5, 5]}})
    assert store.resolve(amap, "btn2") == (12, 22)


def test_resolve_unknown_name_lists_available():
    """Test that resolving an unknown button name lists available buttons."""
    amap = ActionMap(lens="test", buttons={"a": {"point": [0, 0]}, "b": {"point": [0, 0]}})
    with pytest.raises(KeyError) as excinfo:
        store.resolve(amap, "zz")
    assert "['a', 'b']" in str(excinfo.value)


def test_resolve_both_keys_raises():
    """Test that a button with both point and rect raises ValueError."""
    amap = ActionMap(lens="test", buttons={"btn": {"point": [1, 1], "rect": [0, 0, 2, 2]}})
    with pytest.raises(ValueError, match="has both 'point' and 'rect'"):
        store.resolve(amap, "btn")


def test_resolve_neither_key_raises():
    """Test that a button with neither point nor rect raises ValueError."""
    amap = ActionMap(lens="test", buttons={"btn": {}})
    with pytest.raises(ValueError, match="has neither 'point' nor 'rect'"):
        store.resolve(amap, "btn")


def test_list_buttons_sorted():
    """Test that list_buttons returns a sorted list of button names."""
    amap = ActionMap(lens="test", buttons={
        "b": {"point": [0, 0]},
        "a": {"point": [0, 0]},
        "c": {"point": [0, 0]},
    })
    assert store.list_buttons(amap) == ["a", "b", "c"]


def test_load_tolerates_missing_buttons_key(tmp_path: Path):
    """Test that loading a file without a buttons key gives an empty buttons dict."""
    import json
    path = store.map_path("x", maps_dir=tmp_path)
    path.write_text(json.dumps({"lens": "x"}), encoding="utf-8")

    loaded = store.load("x", maps_dir=tmp_path)
    assert loaded.buttons == {}
