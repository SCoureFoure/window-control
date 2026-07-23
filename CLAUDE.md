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
- `pyautogui` — input synthesis
- `pywin32` — DPI awareness, window enumeration (helper only), foreground hints
- `Pillow` — PNG encode + optional grid overlay draw
- `PyQt6` — lens overlay UI (transparent always-on-top frameless window with drag handles)
- `python-dotenv` — `.env` for `ANTHROPIC_API_KEY`

## Project layout

```
src/
  orchestrator.py        # run loop: capture → perceive → act
  reporter.py            # runs/ artifacts
  lens/
    model.py             # Lens dataclass, screen-abs rect math
    store.py             # load/save ~/.window-control/lens.json
    overlay.py           # PyQt6 draggable lens editor
    grid.py              # optional coord-grid overlay for debugging
  zones/
    capture.py           # mss grab of lens rect → (b64, w, h, origin)
    perception.py        # Anthropic call, parse tool_use, prompt caching
    action.py            # dispatch ParsedAction to active backend
  backends/
    base.py              # InputBackend interface
    desktop.py           # mouse + keyboard via pyautogui
  utils/
    coords.py            # lens-rel → screen-abs, DPI helpers
    windows.py           # optional: snap-lens-to-window helper
tests/
runs/                    # gitignored
scripts/
```

## Conventions

- All paths in code are absolute or `pathlib.Path` from project root.
- Coordinates: tuples `(x, y)`. Rects: `(x, y, w, h)`. Never mix.
- Two coordinate spaces only: **lens-relative** (model speaks this) and **screen-absolute** (OS speaks this). Convert at the boundary in `coords.py`. Never convert anywhere else.
- DPI: process is set to per-monitor DPI-aware on startup. `mss` and `SendInput` agree on physical pixels, so coord math is identity. If a refactor introduces logical-pixel APIs, add a conversion layer — do not sprinkle scale factors.
- Tests run against `pytest`. Mock the Anthropic client at the perception boundary.

## What this project is NOT

- Not a browser automation tool. Selenium, Playwright, CDP are out of scope.
- Not an Appium replacement. No device farms, no platform drivers.
- Not a screen reader or a11y client. We use pixels, not the a11y tree.
- Not an RPA platform. No flow designer, no scheduler, no record-and-replay.
- Not multi-agent. One lens, one loop, one model per run.

## Working on this repo

- Use `/delegate` as the entry point for all development work on this repo — implementation, refactors, bug fixes, and feature builds. It routes work through the horde to the cheapest capable agent tier and judges by the verify command.
- When in doubt about scope, re-read "Core invariants" above and ask before deviating.
- Refactors that violate an invariant need a written justification in the PR description.
- New action types go through `InputBackend`. New perception strategies go through `zones/perception.py`. New capture sources go through `zones/capture.py`. Do not bypass.
