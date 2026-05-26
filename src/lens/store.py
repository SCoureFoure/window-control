"""Persist named lenses to ~/.window-control/lenses.json.

Multiple lenses live in a single JSON object keyed by name. Default lens name
is "default". The directory is created lazily on first save.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.lens.model import Lens

CONFIG_DIR = Path.home() / ".window-control"
LENSES_PATH = CONFIG_DIR / "lenses.json"
DEFAULT_NAME = "default"


def _ensure_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_all(path: Path = LENSES_PATH) -> dict[str, Lens]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {name: Lens.from_dict({**d, "name": name}) for name, d in raw.items()}


def save_all(lenses: dict[str, Lens], path: Path = LENSES_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialised = {name: {k: v for k, v in lens.to_dict().items() if k != "name"}
                  for name, lens in lenses.items()}
    path.write_text(json.dumps(serialised, indent=2), encoding="utf-8")


def load(name: str = DEFAULT_NAME, path: Path = LENSES_PATH) -> Lens | None:
    return load_all(path).get(name)


def save(lens: Lens, path: Path = LENSES_PATH) -> None:
    lenses = load_all(path)
    lenses[lens.name] = lens
    save_all(lenses, path)


def delete(name: str, path: Path = LENSES_PATH) -> bool:
    lenses = load_all(path)
    if name not in lenses:
        return False
    del lenses[name]
    save_all(lenses, path)
    return True


def list_names(path: Path = LENSES_PATH) -> list[str]:
    return sorted(load_all(path).keys())
