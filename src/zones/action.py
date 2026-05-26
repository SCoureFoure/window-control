"""Action zone — translate a ParsedAction into backend input calls.

Coordinates from the model are lens-relative. We convert to screen-absolute
using the Lens, bounds-check, then dispatch via the backend. The orchestrator
chooses which backend to use; this module never instantiates one.
"""

from __future__ import annotations

from src.backends.base import InputBackend
from src.lens.model import Lens
from src.zones.perception import ParsedAction


class OutOfBoundsError(Exception):
    """Raised when an action references a coordinate outside the lens."""


def execute(action: ParsedAction, lens: Lens, backend: InputBackend) -> None:
    handler = _HANDLERS.get(action.action)
    if handler is None:
        print(f"  [action] unknown action {action.action!r} — skipping")
        return
    handler(action, lens, backend)


def _to_screen(lens: Lens, coord: tuple[int, int] | None, field_name: str) -> tuple[int, int]:
    if coord is None:
        raise ValueError(f"missing {field_name}")
    try:
        return lens.to_screen(coord[0], coord[1])
    except ValueError as e:
        raise OutOfBoundsError(str(e)) from e


def _left_click(a: ParsedAction, lens: Lens, b: InputBackend) -> None:
    x, y = _to_screen(lens, a.coordinate, "coordinate")
    b.click(x, y, button="left")


def _right_click(a: ParsedAction, lens: Lens, b: InputBackend) -> None:
    x, y = _to_screen(lens, a.coordinate, "coordinate")
    b.click(x, y, button="right")


def _middle_click(a: ParsedAction, lens: Lens, b: InputBackend) -> None:
    x, y = _to_screen(lens, a.coordinate, "coordinate")
    b.click(x, y, button="middle")


def _double_click(a: ParsedAction, lens: Lens, b: InputBackend) -> None:
    x, y = _to_screen(lens, a.coordinate, "coordinate")
    b.double_click(x, y)


def _triple_click(a: ParsedAction, lens: Lens, b: InputBackend) -> None:
    x, y = _to_screen(lens, a.coordinate, "coordinate")
    b.triple_click(x, y)


def _mouse_move(a: ParsedAction, lens: Lens, b: InputBackend) -> None:
    x, y = _to_screen(lens, a.coordinate, "coordinate")
    b.mouse_move(x, y)


def _left_click_drag(a: ParsedAction, lens: Lens, b: InputBackend) -> None:
    x1, y1 = _to_screen(lens, a.start_coordinate or a.coordinate, "start_coordinate")
    x2, y2 = _to_screen(lens, a.coordinate, "coordinate")
    duration = a.duration if a.duration is not None else 0.3
    b.swipe(x1, y1, x2, y2, duration=duration)


def _left_mouse_down(a: ParsedAction, lens: Lens, b: InputBackend) -> None:
    x, y = _to_screen(lens, a.coordinate, "coordinate")
    b.mouse_down(x, y, button="left")


def _left_mouse_up(a: ParsedAction, lens: Lens, b: InputBackend) -> None:
    x, y = _to_screen(lens, a.coordinate, "coordinate")
    b.mouse_up(x, y, button="left")


def _scroll(a: ParsedAction, lens: Lens, b: InputBackend) -> None:
    x, y = _to_screen(lens, a.coordinate, "coordinate")
    direction = a.scroll_direction or "down"
    b.scroll(x, y, direction=direction, amount=a.scroll_distance)


def _type_text(a: ParsedAction, _lens: Lens, b: InputBackend) -> None:
    if not a.text:
        print("  [action] type missing text — skipping")
        return
    b.type_text(a.text)


def _key(a: ParsedAction, _lens: Lens, b: InputBackend) -> None:
    keys = a.keys or ([a.text] if a.text else [])
    if not keys:
        print("  [action] key missing keys — skipping")
        return
    b.key(keys)


def _hold_key(a: ParsedAction, _lens: Lens, b: InputBackend) -> None:
    keys = a.keys or ([a.text] if a.text else [])
    if not keys:
        print("  [action] hold_key missing keys — skipping")
        return
    duration = a.duration if a.duration is not None else 1.0
    for k in keys:
        b.hold_key(k, duration)


def _wait(a: ParsedAction, _lens: Lens, b: InputBackend) -> None:
    duration = a.duration if a.duration is not None else 1.0
    b.wait(duration)


def _screenshot(_a: ParsedAction, _lens: Lens, _b: InputBackend) -> None:
    # No-op here — the orchestrator handles re-capture before the next turn.
    return


_HANDLERS = {
    "left_click": _left_click,
    "right_click": _right_click,
    "middle_click": _middle_click,
    "double_click": _double_click,
    "triple_click": _triple_click,
    "mouse_move": _mouse_move,
    "left_click_drag": _left_click_drag,
    "left_mouse_down": _left_mouse_down,
    "left_mouse_up": _left_mouse_up,
    "scroll": _scroll,
    "type": _type_text,
    "key": _key,
    "hold_key": _hold_key,
    "wait": _wait,
    "screenshot": _screenshot,
}
