"""Tests for src/zones/action.py — backend is mocked."""

from unittest.mock import MagicMock

import pytest

from src.lens.model import Lens
from src.zones.action import OutOfBoundsError, execute
from src.zones.perception import ParsedAction


def _make_lens() -> Lens:
    return Lens(name="t", x=1000, y=2000, w=500, h=400)


def _action(action_type: str, **kwargs) -> ParsedAction:
    base = {"tool_use_id": "t1", "action": action_type, "keys": []}
    base.update(kwargs)
    return ParsedAction(**base)


@pytest.fixture()
def backend() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def lens() -> Lens:
    return _make_lens()


class TestClicks:
    def test_left_click_translates_to_screen(self, lens, backend):
        execute(_action("left_click", coordinate=(50, 75)), lens, backend)
        backend.click.assert_called_once_with(1050, 2075, button="left")

    def test_right_click(self, lens, backend):
        execute(_action("right_click", coordinate=(0, 0)), lens, backend)
        backend.click.assert_called_once_with(1000, 2000, button="right")

    def test_double_click(self, lens, backend):
        execute(_action("double_click", coordinate=(10, 10)), lens, backend)
        backend.double_click.assert_called_once_with(1010, 2010)


class TestDrag:
    def test_left_click_drag_uses_start_and_end(self, lens, backend):
        execute(
            _action(
                "left_click_drag",
                start_coordinate=(10, 10),
                coordinate=(100, 100),
                duration=0.5,
            ),
            lens,
            backend,
        )
        backend.swipe.assert_called_once_with(1010, 2010, 1100, 2100, duration=0.5)

    def test_drag_default_duration(self, lens, backend):
        execute(
            _action("left_click_drag", start_coordinate=(0, 0), coordinate=(50, 50)),
            lens,
            backend,
        )
        backend.swipe.assert_called_once_with(1000, 2000, 1050, 2050, duration=0.3)


class TestScroll:
    def test_scroll_up(self, lens, backend):
        execute(
            _action("scroll", coordinate=(10, 10), scroll_direction="up", scroll_distance=5),
            lens,
            backend,
        )
        backend.scroll.assert_called_once_with(1010, 2010, direction="up", amount=5)

    def test_scroll_default_direction(self, lens, backend):
        execute(_action("scroll", coordinate=(0, 0)), lens, backend)
        backend.scroll.assert_called_once_with(1000, 2000, direction="down", amount=3)


class TestText:
    def test_type(self, lens, backend):
        execute(_action("type", text="hello"), lens, backend)
        backend.type_text.assert_called_once_with("hello")

    def test_type_missing_text_skips(self, lens, backend):
        execute(_action("type"), lens, backend)
        backend.type_text.assert_not_called()

    def test_key_combo(self, lens, backend):
        execute(_action("key", keys=["ctrl", "s"]), lens, backend)
        backend.key.assert_called_once_with(["ctrl", "s"])

    def test_key_text_fallback(self, lens, backend):
        execute(_action("key", text="Return"), lens, backend)
        backend.key.assert_called_once_with(["Return"])


class TestWait:
    def test_wait_default(self, lens, backend):
        execute(_action("wait"), lens, backend)
        backend.wait.assert_called_once_with(1.0)

    def test_wait_with_duration(self, lens, backend):
        execute(_action("wait", duration=2.5), lens, backend)
        backend.wait.assert_called_once_with(2.5)


class TestBounds:
    def test_out_of_bounds_raises(self, lens, backend):
        with pytest.raises(OutOfBoundsError):
            execute(_action("left_click", coordinate=(9999, 9999)), lens, backend)
        backend.click.assert_not_called()


class TestScreenshot:
    def test_screenshot_is_noop(self, lens, backend):
        execute(_action("screenshot"), lens, backend)
        for name in ("click", "swipe", "type_text", "key", "scroll", "wait"):
            getattr(backend, name).assert_not_called()


class TestUnknown:
    def test_unknown_action_skips(self, lens, backend):
        execute(_action("teleport"), lens, backend)
        backend.click.assert_not_called()
