"""Tests for the snap-lens-to-window helper. All win32gui calls are mocked."""

from unittest import mock

import pytest

from src.utils.windows import snap_lens_to_window


def make_win32gui(windows):
    # windows: list of dicts {hwnd, visible, title, rect}
    m = mock.MagicMock()

    def enum(callback, extra):
        for w in windows:
            callback(w["hwnd"], extra)

    m.EnumWindows.side_effect = enum
    by_hwnd = {w["hwnd"]: w for w in windows}
    m.IsWindowVisible.side_effect = lambda h: by_hwnd[h]["visible"]
    m.GetWindowText.side_effect = lambda h: by_hwnd[h]["title"]
    m.GetWindowRect.side_effect = lambda h: by_hwnd[h]["rect"]
    return m


def test_found_exactly_one_match():
    windows = [
        {"hwnd": 1, "visible": True, "title": "Notepad", "rect": (0, 0, 10, 10)},
        {"hwnd": 2, "visible": True, "title": "MyGame - Emulator", "rect": (100, 200, 500, 700)},
        {"hwnd": 3, "visible": False, "title": "MyGame - Hidden", "rect": (0, 0, 10, 10)},
    ]
    with mock.patch("src.utils.windows.win32gui", make_win32gui(windows)):
        lens = snap_lens_to_window("mygame", name="mine")

    assert lens.name == "mine"
    assert lens.x == 100
    assert lens.y == 200
    assert lens.w == 400
    assert lens.h == 500


def test_not_found_zero_matches():
    windows = [
        {"hwnd": 1, "visible": True, "title": "Notepad", "rect": (0, 0, 10, 10)},
        {"hwnd": 2, "visible": False, "title": "MyGame - Emulator", "rect": (0, 0, 10, 10)},
    ]
    with mock.patch("src.utils.windows.win32gui", make_win32gui(windows)):
        with pytest.raises(ValueError) as exc_info:
            snap_lens_to_window("mygame")

    assert "no visible window" in str(exc_info.value)


def test_multiple_matches():
    windows = [
        {"hwnd": 1, "visible": True, "title": "MyGame - Window A", "rect": (0, 0, 10, 10)},
        {"hwnd": 2, "visible": True, "title": "MyGame - Window B", "rect": (0, 0, 10, 10)},
    ]
    with mock.patch("src.utils.windows.win32gui", make_win32gui(windows)):
        with pytest.raises(ValueError) as exc_info:
            snap_lens_to_window("mygame")

    assert "multiple windows" in str(exc_info.value)
