"""Action allowlist — guards which action types the orchestrator may execute.

Default: all actions registered in zones/action.py are permitted.
Restrict at runtime via --allow or --no-typing CLI flags.
"""

from __future__ import annotations

# Mirrors the keys in zones/action._HANDLERS.  Kept here as the single source
# of truth so callers don't have to import from zones/action.
ALL_ACTIONS: frozenset[str] = frozenset({
    "left_click",
    "right_click",
    "middle_click",
    "double_click",
    "triple_click",
    "mouse_move",
    "left_click_drag",
    "left_mouse_down",
    "left_mouse_up",
    "scroll",
    "type",
    "key",
    "hold_key",
    "wait",
    "screenshot",
})

TYPING_ACTIONS: frozenset[str] = frozenset({"type", "key"})

ALLOWED_ACTIONS: set[str] = set(ALL_ACTIONS)


def restrict(allowed: set[str]) -> None:
    """Replace the global allowlist in-place."""
    global ALLOWED_ACTIONS
    ALLOWED_ACTIONS = set(allowed)


def is_allowed(action: str) -> bool:
    return action in ALLOWED_ACTIONS


def parse_allow_flag(value: str) -> set[str]:
    """Parse a comma-separated action list from --allow.  Raises ValueError on unknown names."""
    requested = {a.strip() for a in value.split(",") if a.strip()}
    unknown = requested - ALL_ACTIONS
    if unknown:
        raise ValueError(f"Unknown action(s): {', '.join(sorted(unknown))}")
    return requested
