"""Tests for src/backends/desktop.py — pyautogui is mocked."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def pg(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("src.backends.desktop.pyautogui", mock)
    monkeypatch.setattr("src.backends.desktop.time.sleep", MagicMock())
    return mock


@pytest.fixture()
def backend(pg):
    from src.backends.desktop import DesktopBackend
    return DesktopBackend()


def test_click(pg, backend):
    backend.click(10, 20)
    pg.click.assert_called_once_with(x=10, y=20, button="left")


def test_click_right(pg, backend):
    backend.click(10, 20, button="right")
    pg.click.assert_called_once_with(x=10, y=20, button="right")


def test_double_click(pg, backend):
    backend.double_click(5, 5)
    pg.doubleClick.assert_called_once_with(x=5, y=5)


def test_long_press_down_then_up(pg, backend):
    backend.long_press(50, 50, duration=0.5)
    pg.moveTo.assert_called_once_with(50, 50)
    pg.mouseDown.assert_called_once_with(button="left")
    pg.mouseUp.assert_called_once_with(button="left")


def test_swipe(pg, backend):
    backend.swipe(0, 0, 100, 100, duration=0.2)
    assert pg.moveTo.call_count == 2
    pg.moveTo.assert_any_call(0, 0)
    pg.moveTo.assert_any_call(100, 100, duration=0.2)
    pg.mouseDown.assert_called_once_with(button="left")
    pg.mouseUp.assert_called_once_with(button="left")


def test_scroll_up_positive(pg, backend):
    backend.scroll(10, 10, "up", 3)
    pg.moveTo.assert_called_once_with(10, 10)
    pg.scroll.assert_called_once_with(3)


def test_scroll_down_negative(pg, backend):
    backend.scroll(10, 10, "down", 3)
    pg.scroll.assert_called_once_with(-3)


def test_type_text(pg, backend):
    backend.type_text("hello")
    pg.typewrite.assert_called_once_with("hello", interval=0.03)


def test_key_single_uses_press(pg, backend):
    backend.key(["enter"])
    pg.press.assert_called_once_with("enter")
    pg.hotkey.assert_not_called()


def test_key_combo_uses_hotkey(pg, backend):
    backend.key(["ctrl", "s"])
    pg.hotkey.assert_called_once_with("ctrl", "s")
    pg.press.assert_not_called()
