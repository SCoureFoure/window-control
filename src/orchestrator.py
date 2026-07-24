"""window-control orchestrator.

Usage:
    # Define or edit a lens interactively
    python -m src.orchestrator --new-lens [--lens NAME]
    python -m src.orchestrator --edit-lens [--lens NAME]
    python -m src.orchestrator --list-lenses

    # Run an agent against a saved lens
    python -m src.orchestrator "tap the menu button" [--lens NAME] [--grid] [--max-steps N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

from src.backends.base import InputBackend
from src.backends.desktop import DesktopBackend
from src.goals import store as goals_store
from src.lens import store as lens_store
from src.lens.grid import draw_grid
from src.lens.model import Lens
from src.reporter import Reporter
import src.safety as safety
import src.actionmap.store as actionmap_store
from src.utils.coords import set_per_monitor_dpi_aware
from src.zones.action import OutOfBoundsError, execute
from src.zones.capture import capture, encode_png_b64
from src.zones.perception import (
    ParsedAction,
    TerminalResult,
    ask_claude,
    build_system_prompt,
)

DEFAULT_MAX_STEPS = 20


def run(
    goal: str,
    lens: Lens,
    max_steps: int = DEFAULT_MAX_STEPS,
    show_grid: bool = False,
    show_border: bool = False,
) -> str:
    reporter = Reporter(goal=goal, lens=lens)
    backend = DesktopBackend()
    client = anthropic.Anthropic()
    system = build_system_prompt(goal, lens.name, lens.w, lens.h)
    messages: list[dict] = []
    prev_id: str | None = None
    outcome = "error"

    border = None
    if show_border:
        from src.lens.border import AccessBorder
        border = AccessBorder(lens, goal=goal, max_steps=max_steps)
        border.start()

    try:
        for step in range(1, max_steps + 1):
            if border:
                border.set_state("watching", step)
            try:
                img = capture(lens)
            except Exception as exc:
                reporter.on_error(step, exc)
                outcome = "error"
                break

            if show_grid:
                img = draw_grid(img)
            b64 = encode_png_b64(img)
            reporter.on_capture(step, b64, lens.w, lens.h)

            if border:
                border.set_state("thinking", step)
            try:
                result, messages, prev_id = ask_claude(
                    client=client,
                    system=system,
                    messages=messages,
                    screenshot_b64=b64,
                    width=lens.w,
                    height=lens.h,
                    prev_tool_use_id=prev_id,
                )
            except Exception as exc:
                reporter.on_error(step, exc)
                outcome = "error"
                break

            if isinstance(result, TerminalResult):
                reporter.on_terminal(step, result)
                outcome = "done" if result.done else "impossible"
                break

            action: ParsedAction = result
            reporter.on_action(step, action)

            if action.action == "screenshot":
                reporter.on_screenshot_request(step)
                continue

            if not safety.is_allowed(action.action):
                reporter.on_error(step, ValueError(f"action {action.action!r} not in allowlist"))
                continue

            if border:
                border.set_state("acting", step)
            try:
                execute(action, lens, backend)
            except OutOfBoundsError as exc:
                reporter.on_error(step, exc)
                # Don't break — let the model see the next screenshot and recover
            except Exception as exc:
                reporter.on_error(step, exc)
                outcome = "error"
                break
        else:
            reporter.on_max_steps(max_steps)
            outcome = "max_steps"
    finally:
        if border:
            border.stop()

    print(f"\n{reporter.summary()}")
    return outcome


def _cmd_new_lens(name: str) -> int:
    from src.lens.overlay import edit_lens
    lens = edit_lens(existing=None, name=name)
    if lens is None:
        print("Cancelled.")
        return 1
    lens_store.save(lens)
    print(f"Saved lens {name!r} at {lens.rect}")
    return 0


def _cmd_edit_lens(name: str) -> int:
    from src.lens.overlay import edit_lens
    existing = lens_store.load(name)
    lens = edit_lens(existing=existing, name=name)
    if lens is None:
        print("Cancelled.")
        return 1
    lens_store.save(lens)
    print(f"Saved lens {name!r} at {lens.rect}")
    return 0


def _cmd_snap(title: str, name: str) -> int:
    from src.utils.windows import snap_lens_to_window
    try:
        lens = snap_lens_to_window(title, name=name)
    except ValueError as exc:
        print(f"Snap failed: {exc}")
        return 1
    lens_store.save(lens)
    print(f"Snapped lens {name!r} to window {title!r}: {lens.rect}")
    return 0


def _cmd_list_lenses() -> int:
    names = lens_store.list_names()
    if not names:
        print("No saved lenses. Create one with --new-lens.")
        return 0
    for n in names:
        lens = lens_store.load(n)
        if lens:
            print(f"  {n:20s}  {lens.w}x{lens.h} @ ({lens.x}, {lens.y})")
    return 0


def _cmd_list_goals() -> int:
    names = goals_store.list_names()
    if not names:
        print("No saved goals. Save one with --save-goal NAME \"goal text\".")
        return 0
    for n in names:
        text = goals_store.get(n)
        if text:
            print(f"  {n:20s}  {text}")
    return 0


def _cmd_save_goal(name: str, text: str) -> int:
    goals_store.save(name, text)
    print(f"Saved goal {name!r}.")
    return 0


def _cmd_tap(
    button: str,
    lens_name: str,
    *,
    maps_dir: Path | None = None,
    lenses_path: Path | None = None,
    backend: InputBackend | None = None,
) -> int:
    """Execute a deterministic tap from a named button in the action map.

    Returns 0 on success, 1 on any error.
    """
    # Load lens
    lens = lens_store.load(lens_name, path=lenses_path or lens_store.LENSES_PATH)
    if lens is None:
        print(f"No saved lens {lens_name!r}. Create one with:\n"
              f"    python -m src.orchestrator --new-lens --lens {lens_name}")
        return 1

    # Load action map
    try:
        amap = actionmap_store.load(lens_name, maps_dir=maps_dir or actionmap_store.MAPS_DIR)
    except FileNotFoundError as exc:
        print(str(exc))
        return 1

    # Resolve button name to coordinate
    try:
        pt = actionmap_store.resolve(amap, button)
    except KeyError as exc:
        print(exc.args[0])
        return 1
    except ValueError as exc:
        print(str(exc))
        return 1

    # Build and execute action
    action = ParsedAction(
        tool_use_id="tap",
        action="left_click",
        coordinate=pt,
    )

    try:
        execute(action, lens, backend or DesktopBackend())
    except OutOfBoundsError as exc:
        print(f"Tap {button!r} out of bounds: {exc}")
        return 1

    print(f"Tapped {button!r} at lens-rel {pt}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a natural-language agent over a screen lens.",
    )
    parser.add_argument("goal", nargs="?", help="What you want the agent to do")
    parser.add_argument("--lens", default=lens_store.DEFAULT_NAME, help="Lens name (default: 'default')")
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    parser.add_argument("--grid", action="store_true", help="Overlay a coordinate grid on each capture")
    parser.add_argument("--no-border", action="store_true",
                        help="Disable the on-screen access border (shown around the lens during a run)")
    parser.add_argument("--new-lens", action="store_true", help="Open the editor to create a new lens")
    parser.add_argument("--edit-lens", action="store_true", help="Open the editor to modify an existing lens")
    parser.add_argument("--list-lenses", action="store_true", help="Print saved lenses and exit")
    parser.add_argument("--goal-name", default=None, help="Run a saved goal from ~/.window-control/goals.json")
    parser.add_argument("--list-goals", action="store_true", help="Print saved goals and exit")
    parser.add_argument("--save-goal", default=None, help="Save the positional goal under NAME and exit (does not run)")
    parser.add_argument("--allow", default=None, metavar="ACTIONS",
                        help="Comma-separated allowlist of action types (e.g. click,type)")
    parser.add_argument("--no-typing", action="store_true",
                        help="Shortcut: drop 'type' and 'key' from the allowlist")
    parser.add_argument("--snap", default=None, metavar="TITLE",
                        help="Snap a new lens to the visible window whose title contains TITLE, save it under --lens NAME, and exit")
    parser.add_argument("--tap", default=None, metavar="BUTTON",
                        help="Tap a named button from the lens's action map (deterministic, no model call) and exit")
    args = parser.parse_args()

    set_per_monitor_dpi_aware()

    if args.allow:
        try:
            allowed = safety.parse_allow_flag(args.allow)
        except ValueError as exc:
            parser.error(str(exc))
        safety.restrict(allowed)
    if args.no_typing:
        safety.restrict(safety.ALLOWED_ACTIONS - safety.TYPING_ACTIONS)

    if args.snap:
        sys.exit(_cmd_snap(args.snap, args.lens))
    if args.list_lenses:
        sys.exit(_cmd_list_lenses())
    if args.new_lens:
        sys.exit(_cmd_new_lens(args.lens))
    if args.edit_lens:
        sys.exit(_cmd_edit_lens(args.lens))
    if args.list_goals:
        sys.exit(_cmd_list_goals())
    if args.save_goal:
        if not args.goal:
            parser.error("--save-goal requires a goal string")
        sys.exit(_cmd_save_goal(args.save_goal, args.goal))

    if args.tap:
        if args.goal or args.goal_name:
            parser.error("--tap cannot be combined with a goal")
        sys.exit(_cmd_tap(args.tap, args.lens))

    if args.goal and args.goal_name:
        parser.error("goal and --goal-name are mutually exclusive")

    goal = args.goal
    if args.goal_name:
        goal = goals_store.get(args.goal_name)
        if goal is None:
            available = ', '.join(goals_store.list_names()) or '(none)'
            print(f"No saved goal {args.goal_name!r}. Available: {available}")
            sys.exit(1)

    if not goal:
        parser.error("goal is required unless using --goal-name / --new-lens / --edit-lens / --list-lenses / --list-goals")

    lens = lens_store.load(args.lens)
    if lens is None:
        print(f"No saved lens {args.lens!r}. Create one with:\n"
              f"    python -m src.orchestrator --new-lens --lens {args.lens}")
        sys.exit(1)

    run(goal=goal, lens=lens, max_steps=args.max_steps, show_grid=args.grid,
        show_border=not args.no_border)


if __name__ == "__main__":
    main()
