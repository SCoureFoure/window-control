"""YAML script runner — deterministic + vision-loop steps chained together.

A flat script is a YAML file at ``~/.window-control/scripts/<name>.yaml``::

    name: uma-daily        # optional, informational
    lens: uma               # required
    steps:
      - goal: "click the Options icon"
      - tap: settings
      - type: "hello"
      - wait: 1.0
      - swipe: {from: back, to: home, duration: 0.3}
      - key: [ctrl, l]
      - scroll: {at: results, direction: down, amount: 3}
      - run: back-to-home

Each step is a single-key mapping. ``goal`` steps hand control to the full
vision loop (`src.orchestrator.run`); the other steps (``tap``, ``type``,
``wait``, ``swipe``, ``key``, ``scroll``) are deterministic and are translated
into a ``ParsedAction`` and dispatched through the existing
``zones/action.execute`` -> ``InputBackend`` path — no new input code,
bounds-checks intact. ``run: name`` splices another script's steps in place,
resolved before execution (see ``build_plan``).

A script may also live in a project tree under the repo-local
``projects/<project>/...`` (gitignored; see docs/SPEC-project-tree.md).
Tree scripts must not set ``lens:`` — the lens comes from the project root's
``project.yaml`` — and their ``tap``/``swipe``/``scroll``/``run:`` names
resolve lexically via ``src.scripts.tree`` (nearest-wins walk up to the
project root), not from a single flat action map.

Abort-on-first-failure: as soon as any step fails (a non-``"done"`` goal
outcome, an out-of-bounds tap/swipe, or a missing/invalid action-map lookup),
the whole script stops and ``run_script`` returns that failing outcome. This
is a safety default — a script is not allowed to keep clicking blind after a
step went wrong.

Border handling: when ``show_border`` is true, an ``AccessBorder`` is kept
running around the lens for the deterministic stretches of the script. Before
a ``goal`` step the current border is stopped (the vision loop shows its own
border for the duration of that step); after the goal step returns, a fresh
border is created and started for the next deterministic stretch. The
border's step count is the flattened plan length (after ``run:`` expansion).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from src import orchestrator
from src.actionmap import store as actionmap_store
from src.backends.desktop import DesktopBackend
from src.lens import store as lens_store
from src.lens.border import AccessBorder
from src.scripts import tree
from src.utils.coords import set_per_monitor_dpi_aware
from src.zones.action import OutOfBoundsError, execute
from src.zones.perception import ParsedAction

CONFIG_DIR = Path.home() / ".window-control"
SCRIPTS_DIR = CONFIG_DIR / "scripts"
STEP_KEYS = {"goal", "tap", "type", "wait", "swipe", "key", "scroll", "run"}

MAX_CALL_DEPTH = 8


@dataclass
class Script:
    name: str
    lens: str | None
    steps: list[dict]


def script_path(name: str, scripts_dir: Path = SCRIPTS_DIR) -> Path:
    """Return the path to the script file for a given name."""
    return scripts_dir / f"{name}.yaml"


def _validate_step(step, i: int) -> None:
    if not isinstance(step, dict) or len(step) != 1:
        raise ValueError(f"Step {i}: must be a mapping with exactly one key")

    key, value = next(iter(step.items()))
    if key not in STEP_KEYS:
        raise ValueError(f"Step {i}: unknown step key {key!r}")

    if key == "swipe":
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("from"), str)
            or not isinstance(value.get("to"), str)
        ):
            raise ValueError(
                f"Step {i}: 'swipe' must be a mapping with string 'from' and 'to' keys"
            )
    elif key == "wait":
        if not isinstance(value, (int, float)):
            raise ValueError(f"Step {i}: 'wait' must be a number")
    elif key == "key":
        if not isinstance(value, list) or len(value) == 0 or not all(isinstance(k, str) for k in value):
            raise ValueError(f"Step {i}: 'key' must be a non-empty list of strings")
    elif key == "scroll":
        if not isinstance(value, dict):
            raise ValueError(f"Step {i}: 'scroll' must be a mapping")
        if "at" not in value:
            raise ValueError(f"Step {i}: 'scroll' must have an 'at' key")
        at = value["at"]
        if isinstance(at, str):
            # Named location, will be resolved via action map
            pass
        elif isinstance(at, list):
            if len(at) != 2 or not all(isinstance(x, (int, float)) for x in at):
                raise ValueError(f"Step {i}: 'scroll' 'at' must be a string or list of exactly 2 numbers")
        else:
            raise ValueError(f"Step {i}: 'scroll' 'at' must be a string or list of exactly 2 numbers")
        if "direction" in value and value["direction"] not in ("up", "down", "left", "right"):
            raise ValueError(f"Step {i}: 'scroll' 'direction' must be one of up/down/left/right")
        if "amount" in value and not isinstance(value["amount"], int):
            raise ValueError(f"Step {i}: 'scroll' 'amount' must be an int")
    elif key == "run":
        if not isinstance(value, str) or not value:
            raise ValueError(f"Step {i}: 'run' must be a non-empty string")
    else:  # goal, tap, type
        if not isinstance(value, str):
            raise ValueError(f"Step {i}: {key!r} must be a string")


def load_script_file(path: Path, *, in_tree: bool) -> Script:
    """Load and validate a script YAML file at an explicit path.

    ``in_tree=False`` (flat) scripts require a string ``lens`` field, as
    today. ``in_tree=True`` (project-tree) scripts must NOT set ``lens`` (it
    comes from the project root's ``project.yaml``); ``Script.lens`` is
    ``None`` for these.

    Raises:
        FileNotFoundError: If the script file does not exist.
        ValueError: If the script structure or any step is invalid.
    """
    if not path.exists():
        raise FileNotFoundError(f"No script at {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top level must be a mapping")

    if in_tree:
        if "lens" in raw:
            raise ValueError(
                f"{path}: tree scripts must not set 'lens' (it comes from project.yaml)"
            )
        lens: str | None = None
    else:
        lens = raw.get("lens")
        if not isinstance(lens, str):
            raise ValueError(f"{path}: 'lens' is required and must be a string")

    steps = raw.get("steps")
    if not isinstance(steps, list):
        raise ValueError(f"{path}: 'steps' is required and must be a list")

    for i, step in enumerate(steps, start=1):
        _validate_step(step, i)

    script_name = raw.get("name", path.stem)
    return Script(name=script_name, lens=lens, steps=steps)


def load_script(name: str, scripts_dir: Path = SCRIPTS_DIR) -> Script:
    """Load and validate a flat script YAML file by name.

    Raises:
        FileNotFoundError: If the script file does not exist.
        ValueError: If the script structure or any step is invalid.
    """
    return load_script_file(script_path(name, scripts_dir), in_tree=False)


def resolve_spec(
    spec: str,
    projects_dir: Path = tree.PROJECTS_DIR,
    scripts_dir: Path = SCRIPTS_DIR,
) -> tuple[Path, Path | None]:
    """Resolve a script spec (path-form or bare name) to (path, project_root).

    ``project_root`` is ``None`` for a flat script.

    Raises:
        FileNotFoundError: If a path-form spec doesn't exist, or a bare name
            matches nothing.
        ValueError: If a path-form spec is malformed, or a bare name matches
            more than one script.
    """
    if "/" in spec:
        path = tree.locate(spec, projects_dir)
        return path, tree.project_root_of(path, projects_dir)

    tree_hits = tree.search_bare(spec, projects_dir)
    flat_path = scripts_dir / f"{spec}.yaml"
    candidates = list(tree_hits)
    if flat_path.exists():
        candidates.append(flat_path)

    if not candidates:
        raise FileNotFoundError(f"No script {spec!r} in projects or {scripts_dir}")
    if len(candidates) == 1:
        p = candidates[0]
        if p in tree_hits:
            return p, tree.project_root_of(p, projects_dir)
        return p, None
    raise ValueError(f"Ambiguous script {spec!r}. Matches: {sorted(candidates)}")


@dataclass
class PlanStep:
    step: dict
    folder: Path | None          # lexical context for button/run resolution; None = flat
    project_root: Path | None    # None = flat


def build_plan(
    script: Script,
    folder: Path | None,
    project_root: Path | None,
    scripts_dir: Path = SCRIPTS_DIR,
    _stack: tuple[Path, ...] = (),
) -> list[PlanStep]:
    """Expand ``script`` (including nested ``run:`` steps) into a flat plan.

    Non-``run:`` steps become one ``PlanStep`` carrying the current lexical
    context. ``run: name`` resolves its target (via the tree walk in a tree
    context, or ``scripts_dir/<name>.yaml`` in a flat context), loads and
    recursively expands it, and splices the result in place.

    Raises:
        FileNotFoundError: If a flat ``run:`` target does not exist (tree
            targets raise via ``tree.resolve_run_target``).
        ValueError: If a ``run:`` expansion would revisit a script already on
            the call stack, or would exceed a call depth of 8.
    """
    plan: list[PlanStep] = []
    for step in script.steps:
        key = next(iter(step))
        if key != "run":
            plan.append(PlanStep(step=step, folder=folder, project_root=project_root))
            continue

        name = step["run"]
        in_tree = project_root is not None
        if in_tree:
            target = tree.resolve_run_target(name, folder, project_root)
            sub_folder, sub_project_root = target.parent, project_root
        else:
            target = scripts_dir / f"{name}.yaml"
            if not target.exists():
                raise FileNotFoundError(f"No script at {target}")
            sub_folder, sub_project_root = None, None

        resolved = target.resolve()
        if resolved in _stack:
            names = [p.stem for p in (*_stack, resolved)]
            raise ValueError(f"Script cycle: {' -> '.join(names)}")
        if len(_stack) >= MAX_CALL_DEPTH:
            raise ValueError(f"Script call depth exceeds {MAX_CALL_DEPTH}")

        sub_script = load_script_file(target, in_tree=in_tree)
        plan.extend(
            build_plan(
                sub_script, sub_folder, sub_project_root, scripts_dir,
                _stack=_stack + (resolved,),
            )
        )

    return plan


def _resolve_point(amap_or_resolver, name: str) -> tuple[int, int]:
    """Resolve a button name via an ActionMap, or a ``name -> (x, y)`` callable."""
    if callable(amap_or_resolver):
        return amap_or_resolver(name)
    return actionmap_store.resolve(amap_or_resolver, name)


def step_to_action(step: dict, amap) -> ParsedAction | None:
    """Translate a single validated step into a ParsedAction, or None for a goal step.

    ``amap`` is only consulted for ``tap``/``swipe``/``scroll`` steps that use
    named locations. It is either an ``ActionMap`` (flat lookup via
    ``actionmap_store.resolve``, as before) or a ``Callable[[str], tuple[int,
    int]]`` resolver (tree lookup via ``tree.resolve_button``).
    """
    key, value = next(iter(step.items()))

    if key == "goal":
        return None

    if key == "tap":
        point = _resolve_point(amap, value)
        return ParsedAction(tool_use_id="script", action="left_click", coordinate=point)

    if key == "type":
        return ParsedAction(tool_use_id="script", action="type", text=value)

    if key == "wait":
        return ParsedAction(tool_use_id="script", action="wait", duration=value)

    if key == "key":
        return ParsedAction(tool_use_id="script", action="key", keys=value)

    if key == "swipe":
        # key == "swipe"
        start = _resolve_point(amap, value["from"])
        end = _resolve_point(amap, value["to"])
        duration = value.get("duration", 0.3)
        return ParsedAction(
            tool_use_id="script",
            action="left_click_drag",
            start_coordinate=start,
            coordinate=end,
            duration=duration,
        )

    # key == "scroll"
    at = value["at"]
    if isinstance(at, str):
        coordinate = _resolve_point(amap, at)
    else:
        coordinate = (int(at[0]), int(at[1]))
    direction = value.get("direction", "down")
    amount = value.get("amount", 3)
    return ParsedAction(
        tool_use_id="script",
        action="scroll",
        coordinate=coordinate,
        scroll_direction=direction,
        scroll_distance=amount,
    )


def run_script(
    script_name: str,
    max_steps_per_goal: int | None = None,
    show_border: bool = True,
    scripts_dir: Path = SCRIPTS_DIR,
    maps_dir: Path | None = None,
    lenses_path: Path | None = None,
    projects_dir: Path | None = None,
) -> str:
    """Run every step of a script (flat or project-tree) in order.

    Abort on the first failing step.

    Returns "done" if every step completed, else the failing outcome
    ("error" | "impossible" | "max_steps").
    """
    p_dir = projects_dir if projects_dir is not None else tree.PROJECTS_DIR

    try:
        path, project_root = resolve_spec(script_name, p_dir, scripts_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc))
        return "error"

    in_tree = project_root is not None
    try:
        script = load_script_file(path, in_tree=in_tree)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc))
        return "error"

    folder = path.parent if in_tree else None

    if in_tree:
        try:
            cfg = tree.load_project_config(folder, project_root)
        except ValueError as exc:
            print(str(exc))
            return "error"
        lens_name = cfg["lens"]
        effective_max_steps = (
            max_steps_per_goal if max_steps_per_goal is not None
            else cfg.get("max-steps-per-goal", 20)
        )
    else:
        lens_name = script.lens
        effective_max_steps = max_steps_per_goal if max_steps_per_goal is not None else 20

    lens = lens_store.load(lens_name, path=lenses_path or lens_store.LENSES_PATH)
    if lens is None:
        print(f"No saved lens {lens_name!r} for script {script.name!r}.")
        return "error"

    try:
        plan = build_plan(
            script, folder, project_root, scripts_dir,
            _stack=(path.resolve(),),
        )
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc))
        return "error"

    total = len(plan)
    flat_amap = None
    backend = DesktopBackend()

    def _new_border() -> AccessBorder:
        b = AccessBorder(lens, goal=f"script {script.name}", max_steps=total)
        b.start()
        return b

    border: AccessBorder | None = _new_border() if show_border else None

    try:
        for i, ps in enumerate(plan, start=1):
            step = ps.step
            key = next(iter(step))

            if key == "goal":
                if border:
                    border.stop()
                    border = None
                outcome = orchestrator.run(
                    step["goal"],
                    lens,
                    max_steps=effective_max_steps,
                    show_grid=False,
                    show_border=show_border,
                )
                if outcome != "done":
                    print(f"Script aborted at step {i}: goal outcome {outcome!r}")
                    return outcome
                if show_border:
                    border = _new_border()
                continue

            if ps.project_root is not None:
                amap_for_step = lambda name, ps=ps: tree.resolve_button(name, ps.folder, ps.project_root)
            else:
                needs_map = False
                if key in ("tap", "swipe"):
                    needs_map = True
                elif key == "scroll" and isinstance(step[key].get("at"), str):
                    needs_map = True

                if needs_map and flat_amap is None:
                    try:
                        flat_amap = actionmap_store.load(
                            lens_name, maps_dir=maps_dir or actionmap_store.MAPS_DIR
                        )
                    except FileNotFoundError as exc:
                        print(f"Script aborted at step {i}: {exc}")
                        return "error"
                amap_for_step = flat_amap

            if border:
                border.set_state("acting", i)
            try:
                action = step_to_action(step, amap_for_step)
                execute(action, lens, backend)
            except (OutOfBoundsError, KeyError, ValueError) as exc:
                print(f"Script aborted at step {i}: {exc}")
                return "error"
            if border:
                border.set_state("watching", i)

        print(f"Script {script.name!r} finished: {total} steps.")
        return "done"
    finally:
        if border:
            border.stop()


def _list_scripts(scripts_dir: Path, projects_dir: Path) -> None:
    project_specs = []
    if projects_dir.exists():
        for p in projects_dir.rglob("*.yaml"):
            if p.name == "project.yaml":
                continue
            rel = p.relative_to(projects_dir)
            project_specs.append("/".join(rel.with_suffix("").parts))
    project_specs.sort()

    flat_names = sorted(p.stem for p in scripts_dir.glob("*.yaml")) if scripts_dir.exists() else []

    if not project_specs and not flat_names:
        print("No scripts. Put YAML files in ~/.window-control/scripts/.")
        return

    if project_specs:
        print("projects:")
        for spec in project_specs:
            print(f"  {spec}")
    if flat_names:
        print("flat:")
        for n in flat_names:
            print(f"  {n}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a YAML script of deterministic + goal steps over a lens.",
    )
    parser.add_argument(
        "script", nargs="?",
        help="Script spec: a project/task/script path, or a bare name (without .yaml)",
    )
    parser.add_argument(
        "--max-steps", type=int, default=None,
        help="Max steps per goal step. Precedence: this flag > project.yaml's "
             "max-steps-per-goal > default (20).",
    )
    parser.add_argument("--no-border", action="store_true",
                        help="Disable the on-screen access border")
    parser.add_argument("--list", action="store_true", help="List available scripts and exit")
    args = parser.parse_args()

    if args.list:
        _list_scripts(SCRIPTS_DIR, tree.PROJECTS_DIR)
        sys.exit(0)

    if not args.script:
        parser.error("script name is required unless using --list")

    set_per_monitor_dpi_aware()

    outcome = run_script(
        args.script,
        max_steps_per_goal=args.max_steps,
        show_border=not args.no_border,
    )

    sys.exit(0 if outcome == "done" else 1)


if __name__ == "__main__":
    main()
