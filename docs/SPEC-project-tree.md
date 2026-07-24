# Spec (draft): project trees — hierarchical scripts + action maps

Status: **DESIGN ONLY — not approved, not built.** Written 2026-07-23 at the Leader's
request, from the Leader's sketch (shared "menu scripts" and "button maps" at a game's
root, task folders nested beneath, children aware of parent assets).

Two forks were already resolved by the Leader before this spec:

- **Script reuse = composition (`run:` step).** No cross-file YAML merge/`extends:`.
- **Button-name collisions: child overrides parent** (nearest-wins scoping).

Depends on: the 2026-07-23 charter amendment in `CLAUDE.md` (action-aid layer), the
shipped Feature B2 (action maps) and Feature C (script runner). This spec is
organizational — it adds no new action types and no branching.

---

## 1. Layout

```
~/.window-control/projects/
  <project>/                      # e.g. umamusume/
    project.yaml                  # lens binding + defaults; REQUIRED at project root
    buttons.json                  # optional project-level action map (shared "menu" buttons)
    scripts/                      # optional shared scripts (open-options.yaml, ...)
    <task>/                       # e.g. daily-races/ — arbitrary nesting depth
      buttons.json                # optional, task-specific buttons
      <script>.yaml               # scripts live directly in task folders
      <subtask>/                  # deeper specialization allowed, same rules
```

Example, matching the Leader's sketch:

```
projects/umamusume/
  project.yaml
  buttons.json                    # "menu" button map — the red-arrow target
  scripts/
    back-to-home.yaml             # "menu scripts" — the other red-arrow target
    open-options.yaml
  story-missions/
    mission-3.yaml
  careers/
    career-1/career-1.yaml
    career-2/career-2.yaml
  daily-races/
    buttons.json
    daily-races.yaml
    daily-legend-races.yaml
```

## 2. `project.yaml`

```yaml
lens: uma                     # required at project root
max-steps-per-goal: 20        # optional default for goal: steps
```

- Any subfolder MAY contain its own `project.yaml` overriding these values for its
  subtree (nearest-wins, same walk as buttons).
- **Lens-override warning:** button coordinates are lens-relative. A subfolder that
  overrides `lens` must not rely on ancestor `buttons.json` entries unless the two
  lenses share dimensions; the runner prints a warning when a resolved button came
  from a map above a lens override. (Cheap sanity guard, not a hard error.)

## 3. Resolution rules (one rule, applied twice)

**The walk:** from the folder containing the *currently executing script*, up to the
project root. Nearest hit wins.

- **Buttons** — `tap: settings` checks `./buttons.json`, then each ancestor's
  `buttons.json`, ending at `<project>/buttons.json`. First map containing the name
  resolves it (child overrides parent). Name found nowhere → abort with the walk's
  checked paths listed.
- **Scripts** — `run: back-to-home` checks, in order: sibling `*.yaml` in the current
  folder, then each ancestor folder's direct `*.yaml`, then each ancestor's
  `scripts/` subfolder, ending with `<project>/scripts/`. First match wins.

A called script resolves *its* buttons/sub-calls from **its own folder**, not the
caller's (lexical, not dynamic, scoping — a shared script behaves identically no
matter who calls it).

## 4. The `run:` step (composition)

```yaml
steps:
  - run: back-to-home           # execute that script's steps, then continue
  - goal: "open the race menu"
  - tap: daily-race
```

- Sub-script failure aborts the caller with the sub-script's outcome (same
  abort-on-first-failure rule as today).
- **Cycle/depth guard:** call chain max depth 8; revisiting a script already on the
  call stack → immediate `ValueError` naming the cycle. 
- Step numbering in the border label shows the flattened position
  (`step 7/23`), computed after expansion.
- `run:` is a procedure call, not a branch. Conditionals, loops, and parameters stay
  out of scope (charter: no flow logic).

## 4b. Step types `key:` and `scroll:` — APPROVED 2026-07-23 (vision-parity)

Leader decision: scripts may use the same action set the vision loop has — no
broader. `key:` and `scroll:` approved for build, independent of the tree feature
(they extend the flat runner too). The backend and `zones/action.py` already support
both, so this is a `step_to_action` mapping plus schema validation:

```yaml
  - key: [ctrl, l]                    # chord: press together, release
  - key: [enter]                      # single key
  - scroll: {at: results, direction: down, amount: 3}   # "at" = button name or [x, y]
```

- `key:` value is a list of key names → `ParsedAction(action="key", keys=[...])`.
  Covers sendkeys-style entry: tab-through forms, hotkeys, enter/escape.
- `scroll:` maps to the existing `scroll` action; `at` resolves like `tap:` (button
  name via the walk) or accepts a literal `[x, y]` lens-relative pair. `direction`
  in up/down/left/right, `amount` optional (default 3).
- On-screen keyboards need no new step type: map each rendered key as a button,
  tap them in sequence.
- These extend the flat runner too, independent of the project-tree feature —
  buildable as their own small slice even if the tree is deferred.

## 5. Invocation

```
python -m src.scripts.runner umamusume/daily-races/daily-legend-races
python -m src.scripts.runner daily-legend-races          # bare name, if unique
python -m src.scripts.runner --list                      # tree view, projects + flat
```

- Path form: relative to `projects/`, no `.yaml` suffix.
- Bare-name form: searched across all projects **and** the flat `scripts/` dir;
  ambiguous → error listing all matches (no guessing).

## 6. Back-compat

- Flat `~/.window-control/scripts/*.yaml` + `actionmaps/<lens>.json` keep working
  unchanged, indefinitely. A flat script uses today's semantics (its `lens:` field,
  the single flat map). `run:` inside a flat script resolves against the flat
  `scripts/` dir only.
- `goals.json` is untouched by this spec (stays global). A future fork could allow
  per-project goals; not proposed now.

## 7. Implementation shape (when approved)

- `src/scripts/tree.py` — pure resolution module: locate script by path/bare name,
  compute ancestor chain, resolve button name via walk, resolve `run:` target via
  walk, load/merge `project.yaml` defaults. **All pure functions over paths — fully
  unit-testable with `tmp_path` trees, no Qt, no API.**
- `src/scripts/runner.py` — gains: `run:` step type + expansion with cycle guard;
  project-aware loading (lens from `project.yaml` instead of script `lens:` field —
  script-level `lens:` still honored for flat scripts); walk-based button resolve
  replacing single-map load when running from a tree.
- `src/actionmap/store.py` — unchanged (walk lives in `tree.py`, which calls
  `load`/`resolve` per map file).
- Tests: tree fixtures under `tmp_path` covering: nearest-wins button override,
  lexical scoping of called scripts, cycle detection, bare-name ambiguity error,
  lens-override warning, flat-layout regression.

Slices (disjoint, each own tests): (1) `tree.py` resolution pure functions;
(2) runner integration + `run:` expansion; (3) `--list` tree view + bare-name search.

## 8. Decision points — Leader answers 2026-07-23

1. **Layout + walk semantics: APPROVED 2026-07-23** ("top level things drip into
   the scripts or get overridden if there is a local version of a general element").
   Pinned implementation details:
   - Tree `buttons.json` files use a FLAT format — `{"settings": {"point": [x, y]}}`
     (no `lens`/`buttons` wrapper; the lens is the project's). Entry values use the
     same `point`/`rect` forms as Feature B2 maps.
   - Tree scripts must NOT contain a `lens:` key (load error) — lens comes from the
     project root's `project.yaml`. Flat scripts keep their `lens:` field unchanged.
   - `run:` expansion happens FULLY BEFORE execution: the runner builds a flat
     execution plan (each step paired with its source folder for lexical
     resolution), so cycles/depth violations fail up front and the border label's
     `step N/M` uses the flattened count.
2. **Lens override in subfolders: FORBIDDEN.** `lens` is set once, at the project
   root's `project.yaml`. Subfolder `project.yaml` may override other defaults
   (e.g. `max-steps-per-goal`) but a `lens` key there is a load error. Revisit if
   a real case appears.
3. **Shared scripts: `scripts/` folders only.** `run:` targets resolve through
   ancestors' `scripts/` subfolders (nearest first, project root last). Loose
   `.yaml` files in task folders are invocable directly but are NOT `run:` targets.
4. **Step types `key:`/`scroll:`: APPROVED** (see §4b) — built independently of
   the tree.
