"""Persist per-lens action maps with named buttons to ~/.window-control/actionmaps/<lens>.json.

An action map is a table of named buttons with LENS-RELATIVE coordinates.
Resolution to screen-absolute happens later via Lens.to_screen (never here).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path.home() / ".window-control"
MAPS_DIR = CONFIG_DIR / "actionmaps"


@dataclass
class ActionMap:
    lens: str
    buttons: dict[str, dict] = field(default_factory=dict)


def map_path(lens_name: str, maps_dir: Path = MAPS_DIR) -> Path:
    """Return the path to the action map file for a lens."""
    return maps_dir / f"{lens_name}.json"


def load(lens_name: str, maps_dir: Path = MAPS_DIR) -> ActionMap:
    """Load an action map from disk.

    Args:
        lens_name: Name of the lens.
        maps_dir: Directory containing action map files.

    Returns:
        ActionMap instance.

    Raises:
        FileNotFoundError: If the action map file does not exist.
    """
    path = map_path(lens_name, maps_dir)
    if not path.exists():
        raise FileNotFoundError(f"No action map for lens {lens_name!r}. Expected {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    lens_from_file = raw.get("lens", lens_name)
    buttons = raw.get("buttons", {})

    return ActionMap(lens=lens_from_file, buttons=buttons)


def save(amap: ActionMap, maps_dir: Path = MAPS_DIR) -> None:
    """Save an action map to disk.

    Args:
        amap: ActionMap instance to save.
        maps_dir: Directory to save the action map file to.
    """
    maps_dir.mkdir(parents=True, exist_ok=True)
    path = map_path(amap.lens, maps_dir)
    content = {"lens": amap.lens, "buttons": amap.buttons}
    path.write_text(json.dumps(content, indent=2), encoding="utf-8")


def resolve(amap: ActionMap, name: str) -> tuple[int, int]:
    """Resolve a button name to a lens-relative (x, y) point.

    Args:
        amap: ActionMap instance.
        name: Button name.

    Returns:
        Lens-relative (x, y) tuple of integers.

    Raises:
        KeyError: If button name is not found.
        ValueError: If button entry has invalid format.
    """
    if name not in amap.buttons:
        available = sorted(amap.buttons.keys())
        raise KeyError(f"No button {name!r} in action map for lens {amap.lens!r}. Available: {available}")

    button = amap.buttons[name]
    has_point = "point" in button
    has_rect = "rect" in button

    if has_point and has_rect:
        raise ValueError(f"Button {name!r} has both 'point' and 'rect'")

    if not has_point and not has_rect:
        raise ValueError(f"Button {name!r} has neither 'point' nor 'rect'")

    if has_point:
        x, y = button["point"]
        return (int(x), int(y))
    else:  # has_rect
        x, y, w, h = button["rect"]
        return (int(x + w // 2), int(y + h // 2))


def list_buttons(amap: ActionMap) -> list[str]:
    """Return a sorted list of button names in the action map."""
    return sorted(amap.buttons.keys())
