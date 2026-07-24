"""Project-tree resolution — pure path functions, no I/O side effects beyond reads.

Project trees live under ``<repo>/projects/<project>/`` (gitignored — personal
game/app trees are user data; starter examples may ship separately), an
optional deeper layout of shared "menu" scripts/buttons at the project root
with task folders nested beneath. Buttons and ``run:`` script targets both
resolve by a single nearest-wins walk: from the folder containing the
currently executing script, up through each ancestor, ending at the project
root. The lens is fixed for the whole project and is set exactly once, in the
project root's ``project.yaml``.

See docs/SPEC-project-tree.md (§1-§5, §8) for the full design.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from src.actionmap.store import ActionMap, resolve as resolve_in_map

CONFIG_DIR = Path.home() / ".window-control"
# Repo root: src/scripts/tree.py -> parents[2]. Projects are repo-local but
# gitignored (user data in the working tree, not in version control).
PROJECTS_DIR = Path(__file__).resolve().parents[2] / "projects"


def locate(spec: str, projects_dir: Path = PROJECTS_DIR) -> Path:
    """Resolve a path-form script spec like ``"umamusume/daily-races/daily-legend-races"``
    to its YAML file under ``projects_dir``.

    Raises:
        ValueError: If spec has fewer than 2 segments, or contains ``..``.
        FileNotFoundError: If the resolved file does not exist.
    """
    segments = spec.split("/")
    if ".." in segments:
        raise ValueError(f"Script spec {spec!r} must not contain '..'")
    if len(segments) < 2:
        raise ValueError(f"Script spec {spec!r} must be <project>/.../<script>")

    path = projects_dir.joinpath(*segments[:-1]) / f"{segments[-1]}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No script at {path}")
    return path


def search_bare(name: str, projects_dir: Path = PROJECTS_DIR) -> list[Path]:
    """Return every ``<name>.yaml`` file anywhere under ``projects_dir``, sorted."""
    if not projects_dir.exists():
        return []
    return sorted(projects_dir.rglob(f"{name}.yaml"))


def project_root_of(script_path: Path, projects_dir: Path = PROJECTS_DIR) -> Path:
    """Return the project root (``projects_dir/<project>``) containing ``script_path``.

    Raises:
        ValueError: If ``script_path`` is not strictly under ``projects_dir``.
    """
    try:
        relative = script_path.relative_to(projects_dir)
    except ValueError:
        raise ValueError(f"{script_path} is not under {projects_dir}")

    parts = relative.parts
    if len(parts) < 2:
        raise ValueError(f"{script_path} is not under {projects_dir}")

    return projects_dir / parts[0]


def ancestor_chain(folder: Path, project_root: Path) -> list[Path]:
    """Return folders from ``folder`` up to and including ``project_root``, nearest first.

    Raises:
        ValueError: If ``folder`` is not ``project_root`` or under it.
    """
    if folder == project_root:
        return [project_root]

    try:
        relative = folder.relative_to(project_root)
    except ValueError:
        raise ValueError(f"{folder} is not under {project_root}")

    chain = [folder]
    current = folder
    for _ in relative.parts:
        current = current.parent
        chain.append(current)
    return chain


def load_buttons_file(path: Path, lens_label: str) -> ActionMap:
    """Load a FLAT project buttons.json (``{"settings": {"point": [x, y]}, ...}``).

    Raises:
        ValueError: If the parsed JSON is not an object.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: buttons file must be a JSON object")
    return ActionMap(lens=lens_label, buttons=raw)


def resolve_button(name: str, folder: Path, project_root: Path) -> tuple[int, int]:
    """Resolve a button name via nearest-wins walk from ``folder`` up to ``project_root``.

    Raises:
        KeyError: If ``name`` is found in no ancestor's buttons.json.
    """
    checked: list[Path] = []
    for ancestor in ancestor_chain(folder, project_root):
        buttons_path = ancestor / "buttons.json"
        if not buttons_path.exists():
            continue
        checked.append(buttons_path)
        amap = load_buttons_file(buttons_path, lens_label=project_root.name)
        if name in amap.buttons:
            return resolve_in_map(amap, name)

    raise KeyError(f"No button {name!r}. Checked: {checked}")


def resolve_run_target(name: str, folder: Path, project_root: Path) -> Path:
    """Resolve a ``run:`` target via nearest-wins walk of ``scripts/`` subfolders.

    Raises:
        FileNotFoundError: If no ``<ancestor>/scripts/<name>.yaml`` exists.
    """
    checked: list[Path] = []
    for ancestor in ancestor_chain(folder, project_root):
        candidate = ancestor / "scripts" / f"{name}.yaml"
        checked.append(candidate)
        if candidate.exists():
            return candidate

    raise FileNotFoundError(f"No script {name!r} for run:. Checked: {checked}")


def load_project_config(folder: Path, project_root: Path) -> dict:
    """Merge ``project.yaml`` files along the chain, root first, nearer overriding.

    Raises:
        ValueError: If the root's project.yaml is missing/lacks a str 'lens' key,
            if any non-root project.yaml sets 'lens', or if any project.yaml
            parses to a non-dict.
    """
    chain = ancestor_chain(folder, project_root)

    cfg: dict = {}
    for ancestor in reversed(chain):
        path = ancestor / "project.yaml"
        is_root = ancestor == project_root

        if is_root:
            if not path.exists():
                raise ValueError(f"{path}: project root must define 'lens'")
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError(f"{path}: project root must define 'lens'")
            if not isinstance(loaded.get("lens"), str):
                raise ValueError(f"{path}: project root must define 'lens'")
        else:
            if not path.exists():
                continue
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError(f"{path}: project.yaml must be a mapping")
            if "lens" in loaded:
                raise ValueError(f"{path}: 'lens' may only be set at the project root")

        cfg.update(loaded)

    return cfg
