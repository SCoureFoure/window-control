"""Persist named goal strings to ~/.window-control/goals.json.

Multiple goals live in a single JSON object keyed by name. A goal is a saved
natural-language prompt string. The directory is created lazily on first save.
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".window-control"
GOALS_PATH = CONFIG_DIR / "goals.json"


def load_all(path: Path = GOALS_PATH) -> dict[str, str]:
    """Load all goals from the goals.json file.

    Args:
        path: Path to the goals.json file.

    Returns:
        Dictionary mapping goal names to goal text. Empty dict if file missing.
    """
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw


def get(name: str, path: Path = GOALS_PATH) -> str | None:
    """Retrieve a single goal by name.

    Args:
        name: The goal name.
        path: Path to the goals.json file.

    Returns:
        The goal text, or None if not found.
    """
    return load_all(path).get(name)


def save(name: str, text: str, path: Path = GOALS_PATH) -> None:
    """Save or update a goal.

    Performs read-modify-write, creating the config directory if needed.

    Args:
        name: The goal name.
        text: The goal text.
        path: Path to the goals.json file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    goals = load_all(path)
    goals[name] = text
    path.write_text(json.dumps(goals, indent=2), encoding="utf-8")


def delete(name: str, path: Path = GOALS_PATH) -> bool:
    """Delete a goal by name.

    Args:
        name: The goal name.
        path: Path to the goals.json file.

    Returns:
        True if the goal was deleted, False if it did not exist.
    """
    goals = load_all(path)
    if name not in goals:
        return False
    del goals[name]
    path.write_text(json.dumps(goals, indent=2), encoding="utf-8")
    return True


def list_names(path: Path = GOALS_PATH) -> list[str]:
    """List all goal names, sorted.

    Args:
        path: Path to the goals.json file.

    Returns:
        Sorted list of goal names.
    """
    return sorted(load_all(path).keys())
