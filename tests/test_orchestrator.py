"""Tests for src/orchestrator.py — run loop behavior.

All external boundaries mocked:
- capture / encode_png_b64 (capture zone)
- ask_claude (perception zone)
- execute (action zone)
- DesktopBackend, Reporter, anthropic.Anthropic
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from src.lens.model import Lens
from src.orchestrator import run
from src.zones.action import OutOfBoundsError
from src.zones.perception import ParsedAction, TerminalResult

LENS = Lens(name="test", x=0, y=0, w=100, h=100)


def _action(action_type: str, coord: tuple[int, int] = (10, 10)) -> ParsedAction:
    return ParsedAction(tool_use_id="tu_1", action=action_type, coordinate=coord)


def _terminal(done: bool = True) -> TerminalResult:
    return TerminalResult(message="DONE: finished" if done else "IMPOSSIBLE: blocked", done=done)


def _make_ask_claude(results: list) -> MagicMock:
    """Build an ask_claude mock that returns each result in sequence."""
    mock = MagicMock()
    mock.side_effect = [
        (r, [], "tu_1" if isinstance(r, ParsedAction) else None)
        for r in results
    ]
    return mock


def _patches(ask_claude_mock: MagicMock, execute_mock: MagicMock | None = None):
    """Return a list of patch context managers covering all external deps."""
    stub_img = MagicMock()
    patcher_list = [
        patch("src.orchestrator.capture", return_value=stub_img),
        patch("src.orchestrator.encode_png_b64", return_value="b64data"),
        patch("src.orchestrator.ask_claude", ask_claude_mock),
        patch("src.orchestrator.Reporter"),
        patch("src.orchestrator.DesktopBackend"),
        patch("src.orchestrator.anthropic.Anthropic"),
        patch("src.orchestrator.build_system_prompt", return_value="sys"),
    ]
    if execute_mock is not None:
        patcher_list.append(patch("src.orchestrator.execute", execute_mock))
    else:
        patcher_list.append(patch("src.orchestrator.execute"))
    return patcher_list


class _MultiPatch:
    """Simple multi-patch context manager."""
    def __init__(self, patchers):
        self._patchers = patchers
        self.mocks = []

    def __enter__(self):
        self.mocks = [p.start() for p in self._patchers]
        return self.mocks

    def __exit__(self, *args):
        for p in self._patchers:
            p.stop()


# ---------------------------------------------------------------------------
# (a) Loop stops on TerminalResult
# ---------------------------------------------------------------------------

def test_loop_stops_on_done_terminal():
    ask = _make_ask_claude([_action("left_click"), _terminal(done=True)])
    with _MultiPatch(_patches(ask)) as mocks:
        capture_mock = mocks[0]
        run("click something", LENS, max_steps=10)
    # Two iterations: one action, then terminal
    assert capture_mock.call_count == 2


def test_loop_stops_on_impossible_terminal():
    ask = _make_ask_claude([_terminal(done=False)])
    with _MultiPatch(_patches(ask)) as mocks:
        capture_mock = mocks[0]
        run("do thing", LENS, max_steps=10)
    assert capture_mock.call_count == 1


def test_reporter_on_terminal_called():
    ask = _make_ask_claude([_terminal(done=True)])
    with _MultiPatch(_patches(ask)) as mocks:
        reporter_cls = mocks[3]
        run("goal", LENS, max_steps=10)
    reporter_instance = reporter_cls.return_value
    reporter_instance.on_terminal.assert_called_once()


# ---------------------------------------------------------------------------
# (b) screenshot action re-captures without calling execute
# ---------------------------------------------------------------------------

def test_screenshot_action_triggers_recapture():
    ask = _make_ask_claude([_action("screenshot"), _terminal(done=True)])
    execute_mock = MagicMock()
    with _MultiPatch(_patches(ask, execute_mock)) as mocks:
        capture_mock = mocks[0]
        run("goal", LENS, max_steps=10)
    # screenshot turn + terminal turn = 2 captures
    assert capture_mock.call_count == 2


def test_screenshot_action_does_not_call_execute():
    ask = _make_ask_claude([_action("screenshot"), _terminal(done=True)])
    execute_mock = MagicMock()
    with _MultiPatch(_patches(ask, execute_mock)):
        run("goal", LENS, max_steps=10)
    execute_mock.assert_not_called()


# ---------------------------------------------------------------------------
# (c) OutOfBoundsError does not break the loop
# ---------------------------------------------------------------------------

def test_out_of_bounds_does_not_break_loop():
    ask = _make_ask_claude([
        _action("left_click", (999, 999)),  # out-of-bounds coord
        _terminal(done=True),
    ])
    execute_mock = MagicMock(side_effect=[OutOfBoundsError("oob"), None])
    with _MultiPatch(_patches(ask, execute_mock)) as mocks:
        capture_mock = mocks[0]
        reporter_cls = mocks[3]
        run("goal", LENS, max_steps=10)
    # Both steps ran — loop continued past the OOB error
    assert capture_mock.call_count == 2
    reporter_instance = reporter_cls.return_value
    reporter_instance.on_error.assert_called_once()


def test_other_execute_exception_breaks_loop():
    ask = _make_ask_claude([
        _action("left_click"),
        _action("left_click"),  # would be step 2, but loop should break after step 1
    ])
    execute_mock = MagicMock(side_effect=RuntimeError("unexpected"))
    with _MultiPatch(_patches(ask, execute_mock)) as mocks:
        capture_mock = mocks[0]
        run("goal", LENS, max_steps=10)
    # Loop broke after step 1 execute error
    assert capture_mock.call_count == 1


# ---------------------------------------------------------------------------
# (d) --max-steps is honored
# ---------------------------------------------------------------------------

def test_max_steps_honored():
    # Provide more actions than max_steps — loop must stop at max_steps
    ask = _make_ask_claude([_action("left_click")] * 10)
    execute_mock = MagicMock()
    with _MultiPatch(_patches(ask, execute_mock)) as mocks:
        capture_mock = mocks[0]
        reporter_cls = mocks[3]
        run("goal", LENS, max_steps=3)
    assert capture_mock.call_count == 3
    reporter_instance = reporter_cls.return_value
    reporter_instance.on_max_steps.assert_called_once_with(3)


def test_max_steps_one():
    ask = _make_ask_claude([_action("left_click")])
    execute_mock = MagicMock()
    with _MultiPatch(_patches(ask, execute_mock)) as mocks:
        capture_mock = mocks[0]
        run("goal", LENS, max_steps=1)
    assert capture_mock.call_count == 1
    assert execute_mock.call_count == 1


# ---------------------------------------------------------------------------
# Additional: grid overlay passed to draw_grid when show_grid=True
# ---------------------------------------------------------------------------

def test_grid_overlay_applied_when_flag_set():
    ask = _make_ask_claude([_terminal(done=True)])
    patchers = _patches(ask)
    patchers.append(patch("src.orchestrator.draw_grid", return_value=MagicMock()))
    with _MultiPatch(patchers) as mocks:
        draw_grid_mock = mocks[-1]
        run("goal", LENS, max_steps=10, show_grid=True)
    draw_grid_mock.assert_called_once()


def test_grid_overlay_not_applied_by_default():
    ask = _make_ask_claude([_terminal(done=True)])
    patchers = _patches(ask)
    patchers.append(patch("src.orchestrator.draw_grid", return_value=MagicMock()))
    with _MultiPatch(patchers) as mocks:
        draw_grid_mock = mocks[-1]
        run("goal", LENS, max_steps=10, show_grid=False)
    draw_grid_mock.assert_not_called()
