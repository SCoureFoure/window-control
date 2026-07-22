# Handoff — window-control next steps

Read [CLAUDE.md](CLAUDE.md) first. Do not violate the 10 invariants without asking the user.

**Status (2026-07-22):** Refactor stable. **75 tests pass** (`python -m pytest -q`). All deps installed (PyQt6, mss, pyautogui, anthropic, pywin32). Tasks 1, 6, 7, 8, 9 done. Tasks 2–5 remain **manual** GUI / end-to-end smoke checks — they need a human at the keyboard and a live `ANTHROPIC_API_KEY`; they cannot run headless.

---

## Done — do not redo

- **Task 1** — deps installed, tests green.
- **Task 6** — snap-lens-to-window helper (`src/utils/windows.py`, `--snap "Notepad"` CLI flag, `tests/test_windows.py`). Optional helper per CLAUDE.md §1; never wired into the run loop.
- **Task 7** — old-screenshot pruning in `src/zones/perception.py` (`history_window`).
- **Task 8** — action allowlist (`src/safety.py`, `--allow`/`--no-typing` flags in `src/orchestrator.py`).
- **Task 9** — orchestrator loop tests (`tests/test_orchestrator.py`).

---

## Remaining — manual smoke tests (human required)

### Task 2 — Verify the lens overlay launches

```
python -m src.orchestrator --new-lens --lens smoke
```

Expected: a translucent grey full-screen overlay with a red box, eight red drag handles, and a help label top-left.

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

If the overlay does not appear or crashes, likely culprits:
- PyQt6 wheel mismatch for the user's Python version → reinstall.
- Multi-monitor virtual geometry — `QApplication.primaryScreen().virtualGeometry()` should span monitors; if not, sum `QApplication.screens()` rects.

Do **not** rewrite the overlay in tkinter. PyQt6 is locked per CLAUDE.md §6.

### Task 3 — End-to-end smoke run

Prerequisite: `.env` contains `ANTHROPIC_API_KEY=...` (already present).

```
python -m src.orchestrator --new-lens --lens notepad
```
Drag the box over an open Notepad window. Save.

```
python -m src.orchestrator "type the word hello" --lens notepad
```

Expected:
- `runs/<timestamp>/` is created.
- `step_01.png` shows the Notepad lens.
- `trace.jsonl` has at least a `capture` event and an `action` event.
- The word `hello` ends up in Notepad.
- Session ends with `DONE: ...`.

If coordinates miss by a consistent offset, check Task 5 (DPI).

### Task 4 — Grid overlay

```
python -m src.orchestrator "tap the menu button" --lens <gamelens> --grid
```

`runs/<ts>/step_*.png` should have yellow gridlines and `x,y` labels every 100px. If labels render as black boxes, the system is missing `arial.ttf`; the code falls back to `ImageFont.load_default()`, so this is cosmetic.

### Task 5 — DPI sanity check (only if clicks miss)

`src/utils/coords.py` sets per-monitor v2 DPI awareness at startup. With that on, `mss`, `GetWindowRect`, and `pyautogui` all agree on physical pixels — no scaling math.

If a captured screenshot's width does not match the lens width in the log, DPI setup did not stick. Print `ctypes.windll.user32.GetDpiForSystem()` and the lens dims, then diagnose. Do not add ad-hoc scale factors anywhere except `src/utils/coords.py`.

---

## Snap helper reference (Task 6, done)

```
python -m src.orchestrator --snap "Notepad" --lens notepad
```
Finds the single visible window whose title contains `Notepad`, saves a lens matching its rect under `--lens NAME`, exits. Raises a clear error on zero or multiple matches. Still a **helper** — the agent works on lenses spanning multiple windows or empty desktop too.

---

## Out of scope — do not do unless user asks

- ADB / touch-injection / accessibility-tree code (violates CLAUDE.md §2, §3).
- Replacing PyQt6 with tkinter (violates §6).
- Browser automation, Selenium, Playwright (violates "What this project is NOT").
- Multi-agent orchestration, planner/critic split.
- Recording / replay UI.

---

## Files map (memorize before editing)

```
src/
  orchestrator.py          # CLI + run loop
  reporter.py              # runs/ artifacts
  safety.py                # action allowlist
  lens/
    model.py               # Lens dataclass, coord math
    store.py               # JSON persistence
    overlay.py             # PyQt6 editor
    grid.py                # PIL grid overlay
  zones/
    capture.py             # mss → PIL.Image
    perception.py          # Anthropic call + parse + history pruning
    action.py              # ParsedAction → backend dispatch
  backends/
    base.py                # InputBackend protocol
    desktop.py             # pyautogui impl
  utils/
    coords.py              # DPI setup
    windows.py             # snap-lens-to-window helper (optional)
tests/                     # pytest, mock at every external boundary
runs/                      # gitignored
```

When in doubt, re-read `CLAUDE.md` §3 (vision-first), §7 (zone responsibilities), §10 (safety). Ask the user before adding new top-level concepts.
