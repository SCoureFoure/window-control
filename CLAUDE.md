# window-control

Natural-language agent that controls a user-defined rectangular region of the screen by capturing it, asking Claude what to do, and synthesizing mouse + keyboard input at the OS level.

## Core invariants (set in stone)

These shape every design decision. Do not relitigate without explicit user approval.

### 1. The target is a screen rectangle, not a process

- The agent operates on a **lens**: an arbitrary screen-absolute rect `(x, y, w, h)`.
- The lens is **not bound to any HWND, PID, or window class**. It floats over whatever pixels are underneath.
- We never attach to a process, hook a window, or read another app's memory. The agent only sees the screen and only emits OS-level input events.
- A "snap lens to window" helper may exist for convenience but is never required.

### 2. Mouse-as-touch, no platform-specific input layers

- All actions are emitted as standard OS mouse + keyboard events (via `pyautogui` or `SendInput`).
- We do **not** use ADB, touch injection (`InjectTouchInput`), accessibility APIs, or emulator-specific RPC.
- Touch-style gestures (tap, swipe, long-press, drag) are synthesized from mouse primitives. A swipe is mouse-down → move → mouse-up over a duration.
- This must work against any visible region: a mobile-game emulator, a desktop app, a browser tab, a remote-desktop window, a Citrix session, anything.

### 3. Vision-first perception

- The only signal Claude receives about the target region is the rendered pixels.
- No accessibility tree, no DOM scrape, no UIA inspection.
- The model returns coordinates relative to the lens (0,0 = lens top-left).

### 4. Lens coordinate overlay

- During a run, an optional debug grid is drawn over the lens (or burned into the screenshot sent to Claude) to help the model and the human reason about click coordinates.
- The grid is a perception aid, not a functional element. Toggle via flag.

### 5. Lens is user-adjustable and persistent

- The user defines the lens through an interactive overlay: drag corners and edges to resize, drag the body to move.
- The lens persists to `~/.window-control/lens.json` so reopening the tool restores the last region.
- Multiple named lenses are allowed; user picks one at launch.

### 6. Backend abstraction even with one implementation

- Action emission goes through an `InputBackend` interface even though only `DesktopBackend` (mouse + keyboard) exists today.
- This keeps the door open for future backends without rewriting the action zone.
- Do not bake `pyautogui` calls into orchestrator, perception, or capture code.

### 7. Three-zone architecture

The agent loop has exactly three zones. Each is stateless from the orchestrator's perspective.

| Zone | Responsibility | Must not |
|------|----------------|----------|
| **capture** | Grab pixels from the lens region, return base64 PNG + dims + lens origin | Touch Anthropic API, emit input, manage history |
| **perception** | Send screenshot + history to Claude, return next action | Move the mouse, write files, search windows |
| **action** | Translate a `ParsedAction` into OS input events via the active backend | Call Anthropic, capture pixels, mutate session state |

The **orchestrator** owns the loop, the message history, and the reporter. Zones do not call each other.

### 8. Every run is recorded

- Each run writes to `runs/<YYYYMMDD_HHMMSS>/` with step screenshots, a `trace.jsonl`, and a `session.log`.
- The reporter is the only component allowed to write to `runs/`.
- Screenshots are saved post-capture for replay and debugging.

### 9. Anthropic Computer Use beta is the model interface

- Model: `claude-opus-4-8` with beta header `computer-use-2025-11-24` and tool type `computer_20251124` (revisit on model bumps; `claude-sonnet-4-6` + `computer_20250124` was retired — that pairing 400s).
- Use prompt caching on the system prompt. Screenshots use `cache_control: ephemeral` where it pays off.
- One tool call per turn. Multi-action plans are emergent from the loop, not batched.

### 10. Safety defaults

- `pyautogui.FAILSAFE = True` stays on (corner-of-screen abort).
- Every emitted coordinate is bounds-checked against the lens rect before dispatch. Out-of-bounds = drop the action and log.
- `--max-steps` caps the loop. Default 20.
- No action allowlist yet, but the architecture must accommodate one.

## Tech stack

- Python 3.11+
- `anthropic` — model client
- `mss` — fast screen capture
- `pyautogui` — input synthesis (note: `DesktopBackend.click` holds the button
  ~80ms — Unity targets miss zero-duration clicks; do not "simplify" it back)
- `pywin32` — DPI awareness, window enumeration (helper only), foreground hints
- `Pillow` — PNG encode + optional grid overlay draw
- `PyQt6` — lens overlay UI + access border (border runs as a subprocess: QApplication
  must own a process's main thread)
- `PyYAML` — script files
- `python-dotenv` — `.env` for `ANTHROPIC_API_KEY`

## Project layout

```
src/
  orchestrator.py        # CLI + run loop: capture → perceive → act; returns outcome
                         #   ("done"|"impossible"|"error"|"max_steps"); also hosts
                         #   --goal-name/--save-goal/--list-goals and --tap
  reporter.py            # runs/ artifacts
  safety.py              # action allowlist (--allow / --no-typing)
  lens/
    model.py             # Lens dataclass, screen-abs rect math
    store.py             # load/save ~/.window-control/lenses.json
    overlay.py           # PyQt6 draggable lens editor
    grid.py              # optional coord-grid overlay for debugging
    border.py            # access border subprocess: amber watching / blue thinking /
                         #   red acting + step/goal label chip; drawn OUTSIDE the lens
  zones/
    capture.py           # mss grab of lens rect → (b64, w, h, origin)
    perception.py        # Anthropic call, parse tool_use, prompt caching, history pruning
    action.py            # dispatch ParsedAction to active backend (bounds-check here)
  backends/
    base.py              # InputBackend interface
    desktop.py           # mouse + keyboard via pyautogui (80ms click hold)
  goals/
    store.py             # named prompt strings, ~/.window-control/goals.json
  actionmap/
    store.py             # flat per-lens button maps, ~/.window-control/actionmaps/
  scripts/
    runner.py            # YAML script runner: tap/type/wait/swipe/key/scroll/run/goal
    tree.py              # project-tree resolution: nearest-wins buttons, run: targets
  utils/
    coords.py            # DPI setup (per-monitor v2; physical px everywhere)
    windows.py           # optional: snap-lens-to-window helper
tests/                   # pytest, headless; mock at every external boundary
runs/                    # gitignored — per-run screenshots + trace.jsonl
projects/                # gitignored user project trees; projects/example/ is tracked
docs/                    # feature specs (action maps/scripts, project trees)
```

## Conventions

- All paths in code are absolute or `pathlib.Path` from project root.
- Coordinates: tuples `(x, y)`. Rects: `(x, y, w, h)`. Never mix.
- Two coordinate spaces only: **lens-relative** (model speaks this; stored in button
  maps) and **screen-absolute** (OS speaks this). Convert at one boundary
  (`Lens.to_screen`, reached via `zones/action.py`). Never convert anywhere else.
- DPI: process is set to per-monitor DPI-aware on startup. `mss` and `SendInput` agree on physical pixels, so coord math is identity. If a refactor introduces logical-pixel APIs, add a conversion layer — do not sprinkle scale factors.
- Tests run against `pytest` (`python -m pytest -q` is the verify command). Mock the
  Anthropic client at the perception boundary; store/runner tests take injectable
  `path`/`dir` parameters so nothing touches the real home dir.

## Deterministic layer (the sanctioned "action aid")

Built under the amendment below; specs in `docs/`. Quick map:

- **Goals** — saved prompt strings, nothing more. `--save-goal/--goal-name/--list-goals`.
- **Flat button maps** — `~/.window-control/actionmaps/<lens>.json`; one-shot
  `--tap NAME --lens X`. Entries are `{"point": [x, y]}` or `{"rect": [x, y, w, h]}`
  (rect taps its center); coordinates are lens-relative.
- **Scripts** — YAML step lists run by `src/scripts/runner.py`. Step types:
  `tap/type/wait/swipe/key/scroll` (deterministic, free), `run:` (call another
  script; expansion happens fully before execution, cycle-guarded, depth ≤ 8),
  `goal:` (full vision loop; costs API credits). Abort on first failure.
- **Project trees** — `projects/<name>/` (repo-local, gitignored; `projects/example/`
  is the tracked skeleton). `project.yaml` at the root pins the lens (subfolders may
  not override it). Buttons and `run:` targets resolve by a nearest-wins walk from
  the script's folder up to the project root; shared scripts resolve lexically
  (their own folder, not the caller's). `run:` targets come only from ancestors'
  `scripts/` subfolders.
- Working pattern: **vision discovers, human confirms, script replays.** Harvest
  coordinates from `runs/<ts>/trace.jsonl` + step screenshots; keep `goal:` steps
  for anything variable (popups, results, load timing) and as end-of-script verifiers.

## What this project is NOT

- Not a browser automation tool. Selenium, Playwright, CDP are out of scope.
- Not an Appium replacement. No device farms, no platform drivers.
- Not a screen reader or a11y client. We use pixels, not the a11y tree.
- Not an RPA platform. No flow designer, no scheduler.
  - **Amendment (2026-07-23, user-approved):** a bounded deterministic layer is permitted
    as an **action aid** — the execution-side sibling of §4's perception aid. Scope:
    per-lens action maps (named, user-curated, lens-relative coordinates in
    `~/.window-control/actionmaps/<lens>.json`), a one-shot `tap NAME` command, and YAML
    scripts mixing vision-loop `goal:` steps with deterministic `tap/type/wait/swipe`
    steps. Justification: maps are optional, per-lens shortcut caches for buttons the
    human has already confirmed; vision remains the default and the only mode for
    unknown UIs; deterministic steps never feed the model non-pixel hints (§3 intact),
    never bind an HWND (§1), and emit input only through the existing `InputBackend`
    with lens bounds-checks (§2, §10). Still out of scope: recording user input to
    build maps, schedulers, conditional/branching flow logic, and any flow-designer UI.
    Map hints must never be injected into perception (spec path B1 — rejected).
- Not multi-agent. One lens, one loop, one model per run.

## Working on this repo

- Use `/delegate` as the entry point for all development work on this repo — implementation, refactors, bug fixes, and feature builds. It routes work through the horde to the cheapest capable agent tier and judges by the verify command (`python -m pytest -q`).
- When in doubt about scope, re-read "Core invariants" above and ask before deviating.
- Refactors that violate an invariant need a written justification in the PR description.
- New action types go through `InputBackend`. New perception strategies go through `zones/perception.py`. New capture sources go through `zones/capture.py`. New script step types go through `runner.step_to_action` + schema validation. Do not bypass.

## Field notes (hard-won, do not relearn)

- Unity-based targets (e.g. Umamusume) ignore zero-duration synthetic clicks;
  `DesktopBackend.click` holds ~80ms for this. Press-and-hold is the proven form.
- A click that "does nothing" may be hitting an already-active control — verify with
  a button that has a guaranteed visible effect before blaming input synthesis.
- Snap-to-window lenses currently include the OS title bar: vision models will click
  the maximize button (~lens-rel (1230, 30) on the uma lens) and wreck every stored
  coordinate. Re-snap to the client area, or keep chrome out of the lens.
- Stored coordinates are lens-relative: moving/resizing the lens or the target window
  invalidates every button map harvested under the old geometry.
