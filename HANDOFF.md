# Handoff — window-control next steps

Read [CLAUDE.md](CLAUDE.md) first. Do not violate the 10 invariants without asking the user.

Repo is fresh after a full refactor. 50 tests pass. PyQt6 not yet installed.

---

## Task 1 — Install deps and verify

```
pip install -r requirements.txt
python -m pytest -q
```

Expected: `50 passed`. If anything fails, stop and report.

---

## Task 2 — Verify the lens overlay launches

```
python -m src.orchestrator --new-lens --lens smoke
```

Expected: a translucent grey full-screen overlay appears with a red box, eight red drag handles, and a help label top-left.

Manual check:
- Drag the body to move the box.
- Drag a corner / edge handle to resize.
- Press **Enter** → terminal prints `Saved lens 'smoke' at (x, y, w, h)`.
- Press **Esc** instead → terminal prints `Cancelled.`

Then:
```
python -m src.orchestrator --list-lenses
```
Expected: `smoke` listed with dims.

Delete the test lens after:
```
python -c "from src.lens import store; store.delete('smoke')"
```

If the overlay does not appear or crashes, the most likely culprits are:
- PyQt6 wheel mismatch for the user's Python version → reinstall
- Multi-monitor virtual geometry — `QApplication.primaryScreen().virtualGeometry()` should already span monitors; if it does not, switch to summing `QApplication.screens()` rects.

Do **not** rewrite the overlay in tkinter. PyQt6 is locked per CLAUDE.md §6 tech stack.

---

## Task 3 — End-to-end smoke run

Prerequisite: `.env` contains `ANTHROPIC_API_KEY=...`. The existing `.env` already has one.

```
python -m src.orchestrator --new-lens --lens notepad
```
Drag the box over an open Notepad window. Save.

```
python -m src.orchestrator "type the word hello" --lens notepad
```

Expected:
- `runs/<timestamp>/` is created
- `step_01.png` shows the Notepad lens
- `trace.jsonl` has at least a `capture` event and an `action` event
- The word `hello` ends up in Notepad
- Session ends with `DONE: ...`

If the model returns coordinates that miss by a consistent offset, check Task 5 (DPI).

---

## Task 4 — Try the grid overlay

```
python -m src.orchestrator "tap the menu button" --lens <gamelens> --grid
```

The screenshots under `runs/<ts>/step_*.png` should now have yellow gridlines and `x,y` labels every 100px. If the labels render as black boxes with no text, the system is missing `arial.ttf`; the code already falls back to `ImageFont.load_default()`, so this is cosmetic.

---

## Task 5 — DPI sanity check (only if clicks miss)

`src/utils/coords.py` sets per-monitor v2 DPI awareness at orchestrator startup. With that on, `mss`, `GetWindowRect`, and `pyautogui` should all agree on physical pixels and no scaling math is needed.

If a captured screenshot's width does not match the lens width reported in the log, the DPI setup did not stick. Print `ctypes.windll.user32.GetDpiForSystem()` and the lens dimensions, then diagnose. Do not add ad-hoc scale factors anywhere except `src/utils/coords.py`.

---

## Task 6 — Add a "snap lens to window" helper

CLAUDE.md §1 allows an optional helper that snaps a lens to a HWND's rect. Implement in `src/utils/windows.py` (new file):

```python
def snap_lens_to_window(title_substring: str, name: str = "default") -> Lens:
    """Find a visible window by title substring, return a Lens matching its rect."""
```

Use `win32gui.EnumWindows` + `IsWindowVisible` + `GetWindowText` to find it, `GetWindowRect` for the rect. Raise a clear error if no match. Add a CLI flag `--snap "Notepad"` to `src/orchestrator.py` that creates a lens from the snap, saves it under `--lens NAME`, and exits.

Tests: mock `win32gui` calls. Cover found, not-found, and multiple-match cases.

This is a **helper**, never required. The agent must still work on lenses that span multiple windows or empty desktop.

---

## Task 7 — Shrink old screenshots in message history

Right now `src/zones/perception.py` keeps every prior screenshot in `messages`. Token cost grows linearly with steps. Two-stage fix:

1. After N turns (default 4), replace the `image` block inside old `tool_result` entries with `{"type": "text", "text": "(old screenshot omitted)"}`.
2. Keep the most recent K screenshots in full.

Add `history_window: int = 4` to `ask_claude` and prune `messages` in place before sending. Add a perception test that asserts only the last K user messages still carry image blocks.

Do not touch the assistant `tool_use` blocks. Do not drop messages entirely — only swap out image content.

---

## Task 8 — Action allowlist (safety)

Add `src/safety.py` exposing `ALLOWED_ACTIONS: set[str]` defaulting to everything in `src/zones/action.py::_HANDLERS`. The orchestrator should consult it before calling `execute`. Provide a CLI flag `--allow click,type` to restrict to a subset, and `--no-typing` as a shortcut that drops `type` and `key`.

Log dropped actions via `Reporter.on_error`. Do not raise.

---

## Task 9 — Tests for the orchestrator loop

Currently uncovered. Add `tests/test_orchestrator.py` that mocks:
- `capture` → returns a stub `PIL.Image`
- `ask_claude` → returns a scripted sequence of `ParsedAction` / `TerminalResult`
- `DesktopBackend` → MagicMock
- `Reporter` → MagicMock

Verify: (a) loop stops on `TerminalResult`, (b) `screenshot` action triggers re-capture without backend call, (c) `OutOfBoundsError` does not break the loop, (d) `--max-steps` is honored.

---

## Out of scope — do not do unless user asks

- Adding ADB / touch-injection / accessibility-tree code (violates CLAUDE.md §2, §3)
- Replacing PyQt6 with tkinter (violates §6)
- Browser automation, Selenium, Playwright (violates "What this project is NOT")
- Multi-agent orchestration, planner/critic split — not in scope yet
- Recording / replay UI

---

## Files map (memorize before editing)

```
src/
  orchestrator.py          # CLI + run loop
  reporter.py              # runs/ artifacts
  lens/
    model.py               # Lens dataclass, coord math
    store.py               # JSON persistence
    overlay.py             # PyQt6 editor
    grid.py                # PIL grid overlay
  zones/
    capture.py             # mss → PIL.Image
    perception.py          # Anthropic call + parse
    action.py              # ParsedAction → backend dispatch
  backends/
    base.py                # InputBackend protocol
    desktop.py             # pyautogui impl
  utils/
    coords.py              # DPI setup
tests/                     # pytest, mock at every external boundary
runs/                      # gitignored
```

When in doubt, re-read `CLAUDE.md` §3 (vision-first), §7 (zone responsibilities), §10 (safety). Ask the user before adding new top-level concepts.
