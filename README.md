# window-control

Natural-language agent that controls a rectangular region of your screen. You define
a **lens** — any screen rect — and the agent captures its pixels, asks Claude what to
do next, and synthesizes OS-level mouse + keyboard input. No process attachment, no
accessibility APIs, no browser drivers: if you can see it, it can drive it — desktop
apps, game emulators, remote-desktop sessions, anything that renders.

Alongside the vision loop there is a small deterministic layer (an "action aid"):
named button maps and YAML scripts for flows you have already confirmed by hand,
so repeat runs cost nothing.

## Setup

```
pip install -r requirements.txt
echo ANTHROPIC_API_KEY=sk-... > .env
```

Python 3.11+, Windows (DPI-aware; capture and input agree on physical pixels).

## Quickstart

```bash
# 1. Define a lens (drag the box over your target, Enter to save)
python -m src.orchestrator --new-lens --lens my-app

#    ...or snap it to a window by title
python -m src.orchestrator --snap "Notepad" --lens my-app

# 2. Run a goal against it (full vision loop)
python -m src.orchestrator "click the settings icon" --lens my-app

# 3. Watch it work
#    - colored border around the lens: amber = watching, blue = thinking, red = acting
#    - every run is recorded to runs/<timestamp>/ (screenshots + trace.jsonl)
```

Useful flags: `--grid` (burn a coordinate grid into what the model sees),
`--max-steps N`, `--allow click,type` (action allowlist), `--no-typing`, `--no-border`.

## Saved goals

Stop retyping prompts. Goals live in `~/.window-control/goals.json`:

```bash
python -m src.orchestrator --save-goal open-options "click the Options icon"
python -m src.orchestrator --goal-name open-options --lens my-app
python -m src.orchestrator --list-goals
```

## Deterministic layer: buttons and scripts

Vision discovers; you confirm; scripts replay for free.

**Button maps** name lens-relative coordinates you trust (harvest them from a vision
run's `runs/<ts>/trace.jsonl` + screenshots):

```bash
# one-shot tap from a flat per-lens map (~/.window-control/actionmaps/<lens>.json)
python -m src.orchestrator --tap settings --lens my-app
```

**Scripts** mix deterministic steps with vision-loop `goal:` steps:

```yaml
steps:
  - run: go-home              # call a shared script
  - tap: nav-tasks            # named button, resolved nearest-wins
  - type: "hello"
  - key: [ctrl, s]
  - wait: 2.0
  - goal: "dismiss any popups until the task list is visible"   # vision handles variability
```

```bash
python -m src.scripts.runner example/daily-task/daily-task
python -m src.scripts.runner --list
```

**Projects** organize scripts + buttons per app under `projects/` (gitignored — yours
stay local). Shared buttons at the project root drip down to tasks; a task's local
entry overrides the parent's. Start by copying `projects/example/` — see
[projects/README.md](projects/README.md).

## Safety

- `pyautogui` failsafe on: slam the mouse into a screen corner to abort.
- Every coordinate is bounds-checked against the lens before dispatch.
- `--max-steps` caps the loop (default 20); `--allow` restricts action types.
- The access border shows exactly when the agent is acting.

## Architecture (short version)

Three stateless zones — **capture** (mss → PNG), **perception** (Anthropic
computer-use call → next action), **action** (dispatch through an `InputBackend`) —
driven by an orchestrator that owns the loop and the run recorder. Two coordinate
spaces only: lens-relative (model) and screen-absolute (OS), converted at one
boundary. Full invariants and design law: [CLAUDE.md](CLAUDE.md); feature specs in
[docs/](docs/).

## Tests

```
python -m pytest -q
```

External boundaries (Anthropic API, screen, input) are mocked; the suite runs headless.
